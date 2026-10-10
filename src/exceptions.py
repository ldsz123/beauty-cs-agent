"""
自定义异常类
统一错误码和错误响应格式
"""
from fastapi import HTTPException, status


class AppException(Exception):
    """应用基础异常"""

    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(AppException):
    """输入验证错误"""

    def __init__(self, message: str = "Invalid input"):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class RateLimitExceeded(AppException):
    """限流错误"""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class LLMError(AppException):
    """LLM 调用错误"""

    def __init__(self, message: str = "LLM service unavailable"):
        super().__init__(
            code="LLM_ERROR",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class StorageError(AppException):
    """存储错误"""

    def __init__(self, message: str = "Storage service unavailable"):
        super().__init__(
            code="STORAGE_ERROR",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class AuthenticationError(AppException):
    """认证错误"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            code="AUTH_ERROR",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class NotFoundError(AppException):
    """资源不存在"""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )
