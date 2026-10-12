"""
基于 Redis 的滑动窗口限流器
支持按 IP 和按 session 限流
"""
import time
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class RateLimiter:
    """滑动窗口限流器（基于 Redis Sorted Set）"""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._enabled = redis_client is not None

    async def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, dict]:
        """检查是否触发限流，返回 (是否限流, 限流信息)"""
        if not self._enabled or not self._redis:
            return False, {}

        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(f"ratelimit:{key}", 0, window_start)
            pipe.zcard(f"ratelimit:{key}")
            pipe.zadd(f"ratelimit:{key}", {str(now): now})
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
            return False, {}  # 限流器故障时放行


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.limiter = RateLimiter(redis_client)
        self.ip_limit = int(os.environ.get("RATE_LIMIT_IP", "60"))
        self.ip_window = int(os.environ.get("RATE_LIMIT_IP_WINDOW", "60"))
        self.session_limit = int(os.environ.get("RATE_LIMIT_SESSION", "20"))
        self.session_window = int(os.environ.get("RATE_LIMIT_SESSION_WINDOW", "60"))

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "")

        if not path.startswith("/api"):
            return await call_next(request)

        if path in ("/api/health", "/api/health/ready"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        ip_limited, ip_info = await self.limiter.is_rate_limited(
            f"ip:{client_ip}", self.ip_limit, self.ip_window
        )
        if ip_limited:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMIT_EXCEEDED",
                                   "message": "Rate limit exceeded. Please try again later."}},
                headers={"Retry-After": str(self.ip_window)},
            )

        session_id = request.query_params.get("session_id") or request.headers.get("X-Session-ID")
        if session_id:
            sess_limited, _ = await self.limiter.is_rate_limited(
                f"session:{session_id}", self.session_limit, self.session_window
            )
            if sess_limited:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "RATE_LIMIT_EXCEEDED",
                                       "message": "Session rate limit exceeded. Please try again later."}},
                    headers={"Retry-After": str(self.session_window)},
                )

        response = await call_next(request)

        if ip_info:
            response.headers["X-RateLimit-Limit"] = str(ip_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(ip_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(ip_info["reset"])

        return response
