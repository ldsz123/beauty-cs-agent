"""
Prometheus 指标中间件
收集 HTTP 请求指标
"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..utils.metrics import http_requests_total, http_request_duration_seconds


class MetricsMiddleware(BaseHTTPMiddleware):
    """HTTP 请求指标收集中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        # 计算耗时
        duration = time.time() - start_time

        # 记录指标（跳过 metrics 端点自身）
        path = request.scope.get("path", "")
        if path != "/metrics":
            status = str(response.status_code)
            http_requests_total.labels(
                method=request.method,
                path=path,
                status=status,
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                path=path,
            ).observe(duration)

        return response
