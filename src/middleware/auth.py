"""
API Key 认证中间件
所有 /api/* 端点（除 /api/health）需要 X-API-Key 请求头
"""
import os
import secrets
from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_valid_api_keys() -> set[str]:
    """从环境变量加载有效 API Key 列表"""
    keys_str = os.environ.get("API_KEYS", "")
    if not keys_str:
        return set()
    return {k.strip() for k in keys_str.split(",") if k.strip()}


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件"""

    def __init__(self, app, exclude_paths: list[str] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/api/health", "/api/health/ready", "/metrics", "/docs", "/openapi.json", "/redoc"]

    async def dispatch(self, request: Request, call_next):
        # 跳过不需要认证的路径
        if any(request.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # 静态页面和首页不需要认证
        if request.path.startswith("/static") or request.path == "/":
            return await call_next(request)

        api_key = request.headers.get(API_KEY_NAME)
        valid_keys = get_valid_api_keys()

        # 如果没有配置 API Keys，则跳过认证（开发模式）
        if not valid_keys:
            logger.warning("API_KEYS not configured, skipping authentication")
            return await call_next(request)

        if not api_key:
            logger.warning(f"Missing API key from {request.client.host if request.client else 'unknown'}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header",
            )

        if not secrets.compare_digest(api_key, api_key) or api_key not in valid_keys:
            logger.warning(f"Invalid API key from {request.client.host if request.client else 'unknown'}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )

        return await call_next(request)
