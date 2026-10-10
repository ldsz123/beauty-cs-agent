"""
全局异常处理器
统一错误响应格式
"""
import uuid
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from loguru import logger

from ..exceptions import AppException


def get_request_id(request: Request) -> str:
    """获取或生成 request_id"""
    return getattr(request.state, "request_id", str(uuid.uuid4())[:8])


async def app_exception_handler(request: Request, exc: AppException):
    """处理自定义异常"""
    request_id = get_request_id(request)
    logger.warning(f"[{request_id}] {exc.code}: {exc.message}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误"""
    request_id = get_request_id(request)
    errors = []

    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({
            "field": field,
            "message": error["msg"],
        })

    logger.warning(f"[{request_id}] Validation error: {errors}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": errors,
                "request_id": request_id,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """处理未捕获异常"""
    request_id = get_request_id(request)
    logger.exception(f"[{request_id}] Unhandled exception: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
                "request_id": request_id,
            }
        },
    )
