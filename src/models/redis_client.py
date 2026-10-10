"""
Redis 缓存客户端
用于会话缓存、知识库检索缓存、热点数据
"""
import json
import hashlib
from typing import Optional, Any
from loguru import logger

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed, caching disabled")


class RedisCache:
    """Redis 缓存管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", default_ttl: int = 300):
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self._client: Optional[redis.Redis] = None
        self._available = False
    
    async def connect(self):
        """连接 Redis"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, running without cache")
            return
        
        try:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self._client.ping()
            self._available = True
            logger.info(f"Redis connected: {self.redis_url}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, running without cache")
            self._available = False
    
    async def close(self):
        """关闭连接"""
        if self._client:
            await self._client.close()
            self._available = False
    
    def _make_key(self, prefix: str, identifier: str) -> str:
        """生成缓存 key"""
        return f"cs_agent:{prefix}:{identifier}"
    
    def _hash_key(self, text: str) -> str:
        """对文本做哈希（用于长文本的 key）"""
        return hashlib.md5(text.encode()).hexdigest()
    
    # ========== 会话缓存 ==========
    async def cache_session(self, session_id: str, session_data: dict, ttl: int = None):
        """缓存会话数据"""
        if not self._available:
            return
        key = self._make_key("session", session_id)
        await self._client.setex(key, ttl or self.default_ttl, json.dumps(session_data, ensure_ascii=False))
    
    async def get_cached_session(self, session_id: str) -> Optional[dict]:
        """获取缓存的会话"""
        if not self._available:
            return None
        key = self._make_key("session", session_id)
        data = await self._client.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def invalidate_session(self, session_id: str):
        """清除会话缓存"""
        if not self._available:
            return
        key = self._make_key("session", session_id)
        await self._client.delete(key)
    
    # ========== 知识库检索缓存 ==========
    async def cache_kb_result(self, query: str, result: str, ttl: int = 300):
        """缓存知识库检索结果"""
        if not self._available:
            return
        key = self._make_key("kb", self._hash_key(query))
        await self._client.setex(key, ttl, result)
    
    async def get_cached_kb(self, query: str) -> Optional[str]:
        """获取缓存的知识库结果"""
        if not self._available:
            return None
        key = self._make_key("kb", self._hash_key(query))
        return await self._client.get(key)
    
    # ========== 通用缓存 ==========
    async def cache(self, key: str, value: Any, ttl: int = None, prefix: str = "cache"):
        """通用缓存"""
        if not self._available:
            return
        full_key = self._make_key(prefix, key)
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await self._client.setex(full_key, ttl or self.default_ttl, value)
    
    async def get_cache(self, key: str, prefix: str = "cache") -> Optional[str]:
        """通用获取"""
        if not self._available:
            return None
        full_key = self._make_key(prefix, key)
        return await self._client.get(full_key)
    
    async def delete_cache(self, key: str, prefix: str = "cache"):
        """通用删除"""
        if not self._available:
            return
        full_key = self._make_key(prefix, key)
        await self._client.delete(full_key)
    
    # ========== 计数器 ==========
    async def increment(self, key: str, amount: int = 1) -> int:
        """原子递增"""
        if not self._available:
            return 0
        full_key = self._make_key("counter", key)
        return await self._client.incrby(full_key, amount)
    
    async def get_counter(self, key: str) -> int:
        """获取计数器"""
        if not self._available:
            return 0
        full_key = self._make_key("counter", key)
        val = await self._client.get(full_key)
        return int(val) if val else 0
    
    # ========== 健康检查 ==========
    @property
    def is_available(self) -> bool:
        return self._available
    
    async def health_check(self) -> bool:
        """健康检查"""
        if not self._available:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            return False
