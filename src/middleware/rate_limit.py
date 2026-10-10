"""
基于 Redis 的滑动窗口限流器
支持按 IP 和按 session 限流
"""
import time
import os
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class RateLimiter:
    """滑动窗口限流器（基于 Redis Sorted Set）"""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._enabled = redis_client is not None

    async def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, dict]:
        """
        检查是否触发限流

        Returns:
            (is_limited, rate_limit_info)
        """
        if not self._enabled or not self._redis:
            return False, {}

        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self._redis.pipeline()

            # 移除窗口外的旧记录
            pipe.zremrangebyscore(f"ratelimit:{key}", 0, window_start)

            # 获取当前窗口内的请求数
            pipe.zcard(f"ratelimit:{key}")

            # 添加当前请求
            pipe.zadd(f"ratelimit:{key}", {str(now): now})

            # 设置 key 过期时间
            pipe.expire(f"ratelimit:{key}", window_seconds + 1)

            results = await pipe.execute()
            current_count = results[1]

            is_limited = current_count > max_requests

            info = {
                "limit": max_requests,
                "remaining": max(0, max_requests - current_count),
                "reset": int(window_start + window_seconds),
            }

            return is_limited, info

        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            # 限流器故障时放行（fail-open）
            return False, {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.limiter = RateLimiter(redis_client)
        # 从环境变量读取限流配置
        self.ip_limit = int(os.environ.get("RATE_LIMIT_IP", "60"))
        self.ip_window = int(os.environ.get("RATE_LIMIT_IP_WINDOW", "60"))
        self.session_limit = int(os.environ.get("RATE_LIMIT_SESSION", "20"))
        self.session_window = int(os.environ.get("RATE_LIMIT_SESSION_WINDOW", "60"))

    async def dispatch(self, request: Request, call_next):
        # 跳过非 API 路径
        if not request.path.startswith("/api"):
            return await call_next(request)

        # 跳过健康检查和 metrics
        if request.path in ("/api/health", "/api/health/ready", "/metrics"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # IP 限流
        ip_limited, ip_info = await self.limiter.is_rate_limited(
            f"ip:{client_ip}", self.ip_limit, self.ip_window
        )
        if ip_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(self.ip_window)},
            )

        # Session 限流（如果有 session_id）
        session_id = request.query_params.get("session_id") or request.headers.get("X-Session-ID")
        if session_id:
            sess_limited, sess_info = await self.limiter.is_rate_limited(
                f"session:{session_id}", self.session_limit, self.session_window
            )
            if sess_limited:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Session rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(self.session_window)},
                )

        response = await call_next(request)

        # 添加限流响应头
        if ip_info:
            response.headers["X-RateLimit-Limit"] = str(ip_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(ip_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(ip_info["reset"])

        return response
