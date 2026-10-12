"""
API Key 认证中间件
- 内置页面（同源 UI）免认证，方便自带控制台使用
- 外部程序化调用需携带 X-API-Key
"""
import os
import json
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

API_KEY_NAME = "X-API-Key"


def get_valid_api_keys() -> set[str]:
    """从环境变量加载有效 API Key 列表"""
    keys_str = os.environ.get("API_KEYS", "")
    if not keys_str:
        return set()
    return {k.strip() for k in keys_str.split(",") if k.strip()}


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件"""

    # 免认证路径
    EXCLUDE_PREFIXES = ("/api/health", "/metrics", "/docs", "/openapi.json", "/redoc")
    EXCLUDE_PATHS = ("/", "/dashboard", "/admin", "/architecture")

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "")

        # 静态资源与页面
        if path.startswith("/static") or path in self.EXCLUDE_PATHS:
            return await call_next(request)

        # 免认证接口
        if any(path.startswith(p) for p in self.EXCLUDE_PREFIXES):
            return await call_next(request)

        valid_keys = get_valid_api_keys()
        # 未配置 Key 时放行（开发模式）
        if not valid_keys:
            return await call_next(request)

        api_key = request.headers.get(API_KEY_NAME)
        if api_key and api_key in valid_keys:
            return await call_next(request)

        # 内置页面（同源 UI）请求免认证：Referer/Origin 主机与请求主机一致
        host = request.headers.get("host", "")
        ref = request.headers.get("referer") or request.headers.get("origin") or ""
        if host and ref and host in ref:
            return await call_next(request)

        # 认证失败：直接返回 JSON（中间件中不能抛 HTTPException）
        if not api_key:
            logger.warning(f"Missing API key: {path}")
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "AUTH_ERROR", "message": "Missing X-API-Key header"}},
            )

        logger.warning(f"Invalid API key: {path}")
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "AUTH_ERROR", "message": "Invalid API key"}},
        )
