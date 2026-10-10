"""
Prometheus 指标定义和收集
"""
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response


# ========== HTTP 指标 ==========
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ========== LLM 指标 ==========
llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM API calls",
    ["provider", "model", "call_type"],
)

llm_call_duration_seconds = Histogram(
    "llm_call_duration_seconds",
    "LLM API call duration in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "model", "token_type"],  # token_type: prompt/completion/total
)

# ========== 流水线指标 ==========
pipeline_stage_duration_seconds = Histogram(
    "pipeline_stage_duration_seconds",
    "Pipeline stage duration in seconds",
    ["stage"],  # stage: emotion/semantic/entity/vision/kb/response
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ========== 业务指标 ==========
active_sessions = Gauge(
    "active_sessions",
    "Number of active sessions",
)

escalations_total = Counter(
    "escalations_total",
    "Total escalations to human agents",
    ["reason"],
)

messages_total = Counter(
    "messages_total",
    "Total messages processed",
    ["role"],  # role: user/assistant
)

# ========== 应用信息 ==========
app_info = Info(
    "app_info",
    "Application information",
)


def get_metrics_response() -> Response:
    """生成 Prometheus metrics 响应"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
