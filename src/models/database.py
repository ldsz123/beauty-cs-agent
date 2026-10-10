"""
数据库模型层 — SQLAlchemy
定义所有 PostgreSQL 表结构
"""
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, Index, UniqueConstraint,
    create_engine
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship


# ========== 基础类 ==========
class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# ========== 会话相关 ==========
class SessionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ESCALATED = "escalated"


class SessionRecord(Base):
    """会话记录表"""
    __tablename__ = "sessions"
    
    id = Column(String(64), primary_key=True, comment="会话ID")
    user_id = Column(String(64), nullable=True, comment="用户ID")
    status = Column(String(20), default=SessionStatus.ACTIVE.value, comment="会话状态")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    ended_at = Column(DateTime, nullable=True, comment="结束时间")
    emotion_history = Column(JSON, default=list, comment="情感变化历史")
    context = Column(JSON, default=dict, comment="会话上下文")
    unresolved_count = Column(Integer, default=0, comment="连续未解决次数")
    metadata_json = Column("metadata", JSON, default=dict, comment="扩展元数据")
    
    # 关系
    messages = relationship("ConversationRecord", back_populates="session", lazy="selectin")
    
    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_updated_at", "updated_at"),
    )


class ConversationRecord(Base):
    """对话记录表"""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, comment="会话ID")
    role = Column(String(20), nullable=False, comment="角色: user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    timestamp = Column(DateTime, default=datetime.utcnow, comment="消息时间")
    
    # 处理结果（仅 assistant 消息）
    emotion_type = Column(String(20), nullable=True, comment="回复时的情感识别结果")
    emotion_intensity = Column(Integer, nullable=True, comment="情感强度")
    intent = Column(String(40), nullable=True, comment="识别的意图")
    entities = Column(JSON, nullable=True, comment="提取的实体")
    actions = Column(JSON, nullable=True, comment="执行的业务动作")
    need_human = Column(Boolean, default=False, comment="是否需要转人工")
    confidence = Column(Float, nullable=True, comment="置信度")
    processing_time_ms = Column(Integer, nullable=True, comment="处理耗时(ms)")
    
    # 关系
    session = relationship("SessionRecord", back_populates="messages")
    
    __table_args__ = (
        Index("idx_conversations_session_id", "session_id"),
        Index("idx_conversations_timestamp", "timestamp"),
    )


# ========== 知识库相关 ==========
class KnowledgeEntry(Base):
    """知识库条目表"""
    __tablename__ = "knowledge_base"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    category = Column(String(64), nullable=False, comment="分类")
    title = Column(String(256), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="内容")
    tags = Column(JSON, default=list, comment="标签列表")
    embedding = Column(JSON, nullable=True, comment="向量嵌入")
    is_active = Column(Boolean, default=True, comment="是否启用")
    priority = Column(Integer, default=0, comment="优先级")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    __table_args__ = (
        Index("idx_kb_category", "category"),
        Index("idx_kb_is_active", "is_active"),
    )


# ========== 用户相关 ==========
class UserRecord(Base):
    """用户表（缓存/映射，真实用户数据在业务系统）"""
    __tablename__ = "users"
    
    id = Column(String(64), primary_key=True, comment="用户ID")
    nickname = Column(String(64), nullable=True, comment="昵称")
    phone = Column(String(20), nullable=True, comment="手机号")
    level = Column(String(20), default="normal", comment="会员等级")
    total_sessions = Column(Integer, default=0, comment="总会话数")
    satisfaction_score = Column(Float, nullable=True, comment="平均满意度")
    created_at = Column(DateTime, default=datetime.utcnow, comment="首次访问")
    last_active_at = Column(DateTime, default=datetime.utcnow, comment="最后活跃")
    
    __table_args__ = (
        Index("idx_users_phone", "phone"),
    )


# ========== 转人工记录 ==========
class EscalationRecord(Base):
    """转人工记录表"""
    __tablename__ = "escalations"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    session_id = Column(String(64), ForeignKey("sessions.id"), comment="会话ID")
    reason = Column(String(64), nullable=False, comment="转人工原因")
    emotion_type = Column(String(20), nullable=True, comment="当时情感状态")
    emotion_intensity = Column(Integer, nullable=True, comment="情感强度")
    resolved = Column(Boolean, default=False, comment="是否已解决")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    resolved_at = Column(DateTime, nullable=True, comment="解决时间")
    
    __table_args__ = (
        Index("idx_escalations_session_id", "session_id"),
        Index("idx_escalations_created_at", "created_at"),
    )


# ========== 操作日志 ==========
class OperationLog(Base):
    """操作日志表"""
    __tablename__ = "operation_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    session_id = Column(String(64), nullable=True, comment="会话ID")
    action = Column(String(64), nullable=False, comment="操作类型")
    target = Column(String(128), nullable=True, comment="操作目标")
    result = Column(String(20), nullable=True, comment="结果: success/fail")
    detail = Column(JSON, nullable=True, comment="详情")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    __table_args__ = (
        Index("idx_logs_session_id", "session_id"),
        Index("idx_logs_action", "action"),
        Index("idx_logs_created_at", "created_at"),
    )


# ========== 数据库引擎 & 会话工厂 ==========
class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, database_url: str):
        # 异步引擎
        self.engine = create_async_engine(
            database_url,
            echo=False,  # 生产环境设为 False
            pool_size=20,
            max_overflow=10,
            pool_recycle=3600,
        )
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    async def create_tables(self):
        """创建所有表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_tables(self):
        """删除所有表（危险！仅测试用）"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    async def get_session(self) -> AsyncSession:
        """获取数据库会话"""
        async with self.async_session_factory() as session:
            yield session
    
    async def close(self):
        """关闭连接"""
        await self.engine.dispose()
