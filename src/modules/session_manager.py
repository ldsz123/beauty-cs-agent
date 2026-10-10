"""
会话管理
支持：内存模式（默认）/ PostgreSQL 持久化 + Redis 缓存
"""
import time
import json
from typing import Optional
from dataclasses import dataclass, field, asdict
from loguru import logger


@dataclass
class Session:
    """会话数据"""
    session_id: str
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    emotion_history: list = field(default_factory=list)
    unresolved_count: int = 0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


class SessionManager:
    """
    会话管理器
    支持三种模式：
    1. memory — 纯内存（默认，无需配置）
    2. postgres — PostgreSQL 持久化
    3. redis — Redis 缓存 + PostgreSQL 持久化
    """
    
    def __init__(self, 
                 ttl: int = 3600, 
                 max_history: int = 20,
                 db_session_factory=None,
                 redis_cache=None,
                 mode: str = "memory"):
        self.ttl = ttl
        self.max_history = max_history
        self.mode = mode
        self._sessions: dict[str, Session] = {}
        self._db_factory = db_session_factory
        self._redis = redis_cache
        
        logger.info(f"SessionManager initialized (mode={mode})")
    
    async def get_session(self, session_id: str) -> Session:
        """获取或创建会话"""
        if self.mode == "memory":
            return self._get_session_memory(session_id)
        elif self.mode == "redis":
            return await self._get_session_redis(session_id)
        elif self.mode == "postgres":
            return await self._get_session_postgres(session_id)
        else:
            return self._get_session_memory(session_id)
    
    async def update_session(self, session_id: str,
                             user_message: str,
                             assistant_reply: str,
                             emotion_result=None,
                             semantic_result=None):
        """更新会话"""
        if self.mode == "memory":
            self._update_session_memory(session_id, user_message, assistant_reply,
                                        emotion_result, semantic_result)
        elif self.mode == "redis":
            await self._update_session_redis(session_id, user_message, assistant_reply,
                                             emotion_result, semantic_result)
        elif self.mode == "postgres":
            await self._update_session_postgres(session_id, user_message, assistant_reply,
                                                emotion_result, semantic_result)
    
    async def delete_session(self, session_id: str):
        """删除会话"""
        self._sessions.pop(session_id, None)
        
        if self._redis and self._redis.is_available:
            await self._redis.invalidate_session(session_id)
        
        if self._db_factory:
            try:
                from src.models.database import SessionRecord
                async with self._db_factory() as db_session:
                    db_record = await db_session.get(SessionRecord, session_id)
                    if db_record:
                        db_record.status = "closed"
                        db_record.ended_at = __import__('datetime').datetime.utcnow()
                        await db_session.commit()
            except Exception as e:
                logger.error(f"Failed to close session in DB: {e}")
    
    # ========== Memory 模式 ==========
    def _get_session_memory(self, session_id: str) -> Session:
        """内存获取"""
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        
        session = self._sessions[session_id]
        if time.time() - session.updated_at > self.ttl:
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
        
        return session
    
    def _update_session_memory(self, session_id, user_message, assistant_reply,
                               emotion_result, semantic_result):
        """内存更新"""
        session = self._get_session_memory(session_id)
        self._apply_session_update(session, user_message, assistant_reply,
                                   emotion_result, semantic_result)
    
    # ========== Redis 模式 ==========
    async def _get_session_redis(self, session_id: str) -> Session:
        """Redis 缓存获取"""
        # 先查 Redis
        if self._redis and self._redis.is_available:
            cached = await self._redis.get_cached_session(session_id)
            if cached:
                session = Session(**cached)
                if time.time() - session.updated_at <= self.ttl:
                    return session
        
        # 再查 PostgreSQL
        if self._db_factory:
            db_session = await self._load_from_postgres(session_id)
            if db_session:
                # 写入 Redis 缓存
                if self._redis and self._redis.is_available:
                    await self._redis.cache_session(session_id, db_session.to_dict())
                return db_session
        
        # 创建新会话
        return Session(session_id=session_id)
    
    async def _update_session_redis(self, session_id, user_message, assistant_reply,
                                    emotion_result, semantic_result):
        """Redis + PostgreSQL 更新"""
        session = await self._get_session_redis(session_id)
        self._apply_session_update(session, user_message, assistant_reply,
                                   emotion_result, semantic_result)
        
        # 更新 Redis 缓存
        if self._redis and self._redis.is_available:
            await self._redis.cache_session(session_id, session.to_dict())
        
        # 持久化到 PostgreSQL
        await self._save_to_postgres(session, user_message, assistant_reply,
                                     emotion_result, semantic_result)
    
    # ========== PostgreSQL 模式 ==========
    async def _get_session_postgres(self, session_id: str) -> Session:
        """PostgreSQL 获取"""
        if self._db_factory:
            db_session = await self._load_from_postgres(session_id)
            if db_session:
                return db_session
        
        return Session(session_id=session_id)
    
    async def _update_session_postgres(self, session_id, user_message, assistant_reply,
                                       emotion_result, semantic_result):
        """PostgreSQL 更新"""
        session = await self._get_session_postgres(session_id)
        self._apply_session_update(session, user_message, assistant_reply,
                                   emotion_result, semantic_result)
        await self._save_to_postgres(session, user_message, assistant_reply,
                                     emotion_result, semantic_result)
    
    # ========== 通用逻辑 ==========
    def _apply_session_update(self, session: Session, user_message: str,
                              assistant_reply: str, emotion_result, semantic_result):
        """应用会话更新（各模式共用）"""
        session.history.append({
            "role": "user",
            "content": user_message,
            "timestamp": time.time()
        })
        session.history.append({
            "role": "assistant",
            "content": assistant_reply,
            "timestamp": time.time()
        })
        
        if len(session.history) > self.max_history * 2:
            session.history = session.history[-self.max_history * 2:]
        
        if emotion_result:
            session.emotion_history.append({
                "emotion": emotion_result.emotion.value,
                "intensity": emotion_result.intensity.value,
                "timestamp": time.time()
            })
        
        if semantic_result:
            session.context["last_intent"] = semantic_result.primary_intent.value
        
        if semantic_result and semantic_result.primary_intent.value == "complaint":
            session.unresolved_count += 1
        else:
            session.unresolved_count = max(0, session.unresolved_count - 1)
        
        session.updated_at = time.time()
    
    # ========== PostgreSQL 操作 ==========
    async def _load_from_postgres(self, session_id: str) -> Optional[Session]:
        """从 PostgreSQL 加载会话"""
        if not self._db_factory:
            return None
        
        try:
            from src.models.database import SessionRecord, ConversationRecord
            async with self._db_factory() as db:
                result = await db.get(SessionRecord, session_id)
                if not result:
                    return None
                
                # 检查过期
                if result.updated_at:
                    age = (time.time() - result.updated_at.timestamp())
                    if age > self.ttl:
                        return None
                
                # 加载消息历史
                messages = []
                for msg in result.messages[-self.max_history * 2:]:
                    messages.append({
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.timestamp() if msg.timestamp else time.time()
                    })
                
                return Session(
                    session_id=result.id,
                    user_id=result.user_id,
                    created_at=result.created_at.timestamp() if result.created_at else time.time(),
                    updated_at=result.updated_at.timestamp() if result.updated_at else time.time(),
                    history=messages,
                    context=result.context or {},
                    emotion_history=result.emotion_history or [],
                    unresolved_count=result.unresolved_count or 0,
                    metadata=result.metadata_json or {},
                )
        except Exception as e:
            logger.error(f"Failed to load session from PostgreSQL: {e}")
            return None
    
    async def _save_to_postgres(self, session: Session, user_message: str,
                                assistant_reply: str, emotion_result, semantic_result):
        """保存到 PostgreSQL"""
        if not self._db_factory:
            return
        
        try:
            from src.models.database import SessionRecord, ConversationRecord
            from datetime import datetime
            async with self._db_factory() as db:
                # Upsert 会话
                now = datetime.utcnow()
                existing = await db.get(SessionRecord, session.session_id)
                
                if existing:
                    existing.updated_at = now
                    existing.emotion_history = session.emotion_history
                    existing.context = session.context
                    existing.unresolved_count = session.unresolved_count
                else:
                    new_session = SessionRecord(
                        id=session.session_id,
                        user_id=session.user_id,
                        status="active",
                        created_at=datetime.fromtimestamp(session.created_at),
                        updated_at=now,
                        emotion_history=session.emotion_history,
                        context=session.context,
                        unresolved_count=session.unresolved_count,
                    )
                    db.add(new_session)
                
                # 添加用户消息
                user_msg = ConversationRecord(
                    session_id=session.session_id,
                    role="user",
                    content=user_message,
                    timestamp=now,
                )
                db.add(user_msg)
                
                # 添加助手回复
                assistant_msg = ConversationRecord(
                    session_id=session.session_id,
                    role="assistant",
                    content=assistant_reply,
                    timestamp=now,
                    emotion_type=emotion_result.emotion.value if emotion_result else None,
                    emotion_intensity=emotion_result.intensity.value if emotion_result else None,
                    intent=semantic_result.primary_intent.value if semantic_result else None,
                    entities=session.context.get("last_entities"),
                    need_human=emotion_result.need_human if emotion_result else False,
                    confidence=semantic_result.confidence if semantic_result else None,
                )
                db.add(assistant_msg)
                
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save session to PostgreSQL: {e}")
