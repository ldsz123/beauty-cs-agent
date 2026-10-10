"""
结构化日志配置
JSON 格式输出、文件轮转、请求 ID 注入
"""
import sys
import os
import uuid
from pathlib import Path

from loguru import logger


def setup_logging():
    """配置 loguru 日志"""
    # 移除默认 handler
    logger.remove()

    # 从环境变量读取日志级别
    log_level = os.environ.get("LOG_LEVEL", "INFO")

    # JSON 格式输出到 stderr
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        serialize=False,
        backtrace=True,
        diagnose=False,
    )

    # 文件日志（JSON 格式，按天轮转）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        str(log_dir / "app.log"),
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        serialize=True,  # JSON 格式
        rotation="1 days",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )

    # 错误日志单独文件
    logger.add(
        str(log_dir / "error.log"),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        serialize=True,
        rotation="1 days",
        retention="90 days",
        compression="gz",
        encoding="utf-8",
        backtrace=True,
    )

    return logger


def get_request_id() -> str:
    """生成请求 ID"""
    return str(uuid.uuid4())[:8]


def log_with_context(logger, level: str, message: str, **kwargs):
    """带上下文的日志输出"""
    context = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    if context:
        message = f"{message} | {context}"
    getattr(logger, level)(message)
