"""
电商智能客服Agent — FastAPI 入口
支持：memory / postgres / redis 三种存储模式
"""
import os
import uuid
import json
from typing import Optional
from contextlib import asynccontextmanager

# 加载 .env（必须在读取环境变量前）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import yaml
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from .agent_engine import CustomerServiceAgent, AgentResponse
from .models.llm_client import create_llm_client
from .middleware.auth import APIKeyAuthMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.metrics import MetricsMiddleware
from .middleware.error_handler import app_exception_handler, validation_exception_handler, generic_exception_handler
from .exceptions import AppException
from .utils.sanitizer import InputSanitizer, sanitize_input, escape_prompt_input
from .utils.metrics import get_metrics_response, app_info
from .utils.logging_config import setup_logging, get_request_id
from .api.state import state
from .api import admin_routes, kb_routes


# ========== 配置加载 ==========
def load_config() -> dict:
    """加载配置"""
    config_path = os.environ.get("CONFIG_PATH", "config/config.yaml")
    
    config = {
        "app": {
            "name": "电商智能客服Agent",
            "host": os.environ.get("APP_HOST", "0.0.0.0"),
            "port": int(os.environ.get("APP_PORT", "8000")),
        },
        "llm": {
            "provider": os.environ.get("LLM_PROVIDER", "openai"),
            "api_key": os.environ.get("LLM_API_KEY", ""),
            "base_url": os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            "model": os.environ.get("LLM_MODEL", "gpt-4o"),
            "timeout": 30,
        },
        "session_ttl": 3600,
        "max_history": 20,
        "emotion_rule_weight": 0.3,
        "emotion_llm_weight": 0.7,
        "kb_config": {"top_k": 5, "cache_ttl": 300},
        "session_mode": os.environ.get("SESSION_MODE", "memory"),  # memory / postgres / redis
        "kb_mode": os.environ.get("KB_MODE", "builtin"),           # builtin / postgres / redis
        "database_url": os.environ.get("DATABASE_URL", ""),
        "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379"),
    }
    
    # 从 YAML 加载
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = yaml.safe_load(f)
            if file_config:
                # 展开配置值中的 ${ENV_VAR:-default} 占位符
                file_config = _expand_env_vars(file_config)
                # 简单合并
                for key in config:
                    if key in file_config:
                        if isinstance(config[key], dict) and isinstance(file_config[key], dict):
                            config[key].update(file_config[key])
                        else:
                            config[key] = file_config[key]
                # 添加额外 key
                for key in file_config:
                    if key not in config:
                        config[key] = file_config[key]
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}, using defaults")
    
    return config


def _expand_env_vars(obj):
    """递归展开配置中的 ${ENV:-default} / ${ENV} 占位符"""
    import re
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        def _replace(match):
            var, _, default = match.group(1).partition(":-")
            return os.environ.get(var, default if default else "")
        return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?)\}', _replace, obj)
    return obj


# ========== 全局实例 ==========
agent: Optional[CustomerServiceAgent] = None
db_manager = None
redis_cache = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    global agent, db_manager, redis_cache

    # 设置日志
    setup_logging()

    # 设置应用信息指标
    app_info.info({"version": "1.0.0", "name": "电商智能客服Agent"})

    config = load_config()
    logger.info("Starting Customer Service Agent...")
    
    # ====== 初始化数据库 ======
    db_factory = None
    if config["session_mode"] in ("postgres", "redis") or config["kb_mode"] in ("postgres", "redis"):
        if config.get("database_url"):
            from .models.database import DatabaseManager
            db_manager = DatabaseManager(config["database_url"])
            db_factory = db_manager.async_session_factory
            await db_manager.create_tables()
            logger.info("PostgreSQL connected and tables created")
        else:
            logger.warning("SESSION_MODE/KB_MODE requires DATABASE_URL, falling back to memory")
            config["session_mode"] = "memory"
            config["kb_mode"] = "builtin"
    
    # ====== 初始化 Redis ======
    if config["session_mode"] == "redis" or config["kb_mode"] == "redis":
        if config.get("redis_url"):
            from .models.redis_client import RedisCache
            redis_cache = RedisCache(redis_url=config["redis_url"])
            await redis_cache.connect()
            if redis_cache.is_available:
                logger.info("Redis connected")
            else:
                logger.warning("Redis unavailable, falling back to postgres mode")
                if config["session_mode"] == "redis":
                    config["session_mode"] = "postgres" if db_factory else "memory"
                if config["kb_mode"] == "redis":
                    config["kb_mode"] = "postgres" if db_factory else "builtin"
        else:
            logger.warning("SESSION_MODE=redis requires REDIS_URL")
            config["session_mode"] = "postgres" if db_factory else "memory"
            config["kb_mode"] = "postgres" if db_factory else "builtin"
    
    # ====== 初始化 LLM ======
    llm_client = None
    if config["llm"].get("api_key"):
        llm_client = create_llm_client(config["llm"])
        logger.info(f"LLM client: {config['llm']['provider']}/{config['llm']['model']}")
    else:
        logger.warning("No LLM_API_KEY, running in rule-only mode")
    
    # ====== 初始化 Agent ======
    agent_config = {
        **config,
        "llm_client": llm_client,
        "vision_llm_client": llm_client,
        "db_session_factory": db_factory,
        "redis_cache": redis_cache,
    }
    agent = CustomerServiceAgent(agent_config)
    state.agent = agent
    state.db_manager = db_manager
    state.redis_cache = redis_cache
    logger.info(f"Agent ready (session_mode={config['session_mode']}, kb_mode={config['kb_mode']})")
    
    yield

    # ====== 优雅关闭 ======
    logger.info("Shutting down...")

    # 关闭 LLM 客户端连接池
    if agent and agent.config.get("llm_client"):
        try:
            await agent.config["llm_client"].close()
            logger.info("LLM client closed")
        except Exception as e:
            logger.warning(f"Error closing LLM client: {e}")

    # 关闭数据库连接池
    if db_manager:
        try:
            await db_manager.close()
            logger.info("Database connection pool closed")
        except Exception as e:
            logger.warning(f"Error closing database: {e}")

    # 关闭 Redis 连接
    if redis_cache:
        try:
            await redis_cache.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis: {e}")

    logger.info("Shutdown complete")


# ========== FastAPI 应用 ==========
app = FastAPI(
    title="电商智能客服Agent",
    description="基于三级处理流水线的电商智能客服系统（PostgreSQL + Redis）",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置：从环境变量读取允许的源
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "")
if _allowed_origins:
    allowed_origins = [o.strip() for o in _allowed_origins.split(",") if o.strip()]
else:
    allowed_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "X-Session-ID"],
)


# ========== 请求 ID 中间件 ==========
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求生成唯一 ID"""
    request_id = get_request_id()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ========== 请求/响应模型 ==========
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    session_id: Optional[str] = Field(None, max_length=64, description="会话ID")
    user_id: Optional[str] = Field(None, max_length=64, description="用户ID")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        # 检测 prompt injection
        has_injection, patterns = InputSanitizer.detect_prompt_injection(v)
        if has_injection:
            raise ValueError("Potentially malicious input detected")
        return sanitize_input(v)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return InputSanitizer.sanitize_session_id(v)


class ChatResponse(BaseModel):
    reply: str
    emotion: dict
    intent: str
    intent_confidence: float
    entities: dict
    actions: list
    need_human: bool
    processing_time_ms: int
    session_id: str
    sources: list = []
    trace_id: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_available: bool
    storage_mode: str
    db_connected: bool
    redis_connected: bool


# ========== API 路由 ==========
@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Liveness 探针 — 始终返回 200"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        llm_available=agent.config.get("llm_client") is not None if agent else False,
        storage_mode=agent.session_manager.mode if agent else "unknown",
        db_connected=True,
        redis_connected=True,
    )


@app.get("/api/health/ready")
async def health_ready():
    """Readiness 探针 — 检查所有依赖"""
    checks = {}
    all_ready = True

    # 检查数据库
    if db_manager:
        try:
            from sqlalchemy import text
            async with db_manager.async_session_factory() as session:
                await session.execute(text("SELECT 1"))
                checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {str(e)}"
            all_ready = False
    else:
        checks["database"] = "not_configured"

    # 检查 Redis
    if redis_cache:
        try:
            redis_ok = await redis_cache.health_check()
            checks["redis"] = "ok" if redis_ok else "error: ping failed"
            if not redis_ok:
                all_ready = False
        except Exception as e:
            checks["redis"] = f"error: {str(e)}"
            all_ready = False
    else:
        checks["redis"] = "not_configured"

    # 检查 LLM
    if agent and agent.config.get("llm_client"):
        checks["llm"] = "configured"
    else:
        checks["llm"] = "not_configured"

    status_code = 200 if all_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
        },
    )


@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    return get_metrics_response()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """同步对话接口"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    session_id = request.session_id or str(uuid.uuid4())
    
    response: AgentResponse = await agent.process(
        user_message=request.message,
        session_id=session_id
    )
    
    return ChatResponse(
        reply=response.reply,
        emotion={
            "type": response.emotion_result.emotion.value,
            "intensity": response.emotion_result.intensity.value,
            "confidence": round(response.emotion_result.confidence, 3),
            "triggers": response.emotion_result.triggers,
            "raw_score": response.emotion_result.raw_score,
        },
        intent=response.semantic_result.primary_intent.value,
        intent_confidence=round(response.semantic_result.confidence, 3),
        entities={
            "order_id": response.entities.order_id,
            "tracking_number": response.entities.tracking_number,
            "product_name": response.entities.product_name,
            "phone": response.entities.phone,
            "amount": response.entities.amount,
            "issue_type": response.entities.issue_type,
            "issue_description": response.entities.issue_description,
        },
        actions=response.actions,
        need_human=response.need_human,
        processing_time_ms=response.processing_time_ms,
        session_id=session_id,
        sources=response.sources,
        trace_id=response.trace_id,
    )


@app.post("/api/chat/with-image", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(...),
    session_id: str = Form(None),
    image: UploadFile = File(...)
):
    """带图片的对话接口"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    session_id = session_id or str(uuid.uuid4())
    image_data = await image.read()
    
    response = await agent.process(
        user_message=message,
        session_id=session_id,
        image_data=image_data
    )
    
    return ChatResponse(
        reply=response.reply,
        emotion={"type": response.emotion_result.emotion.value,
                 "intensity": response.emotion_result.intensity.value},
        intent=response.semantic_result.primary_intent.value,
        intent_confidence=round(response.semantic_result.confidence, 3),
        entities=response.entities.raw_entities,
        actions=response.actions,
        need_human=response.need_human,
        processing_time_ms=response.processing_time_ms,
        session_id=session_id,
    )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口（SSE）"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    session_id = request.session_id or str(uuid.uuid4())
    
    async def event_generator():
        yield f"data: {json.dumps({'status': 'processing'}, ensure_ascii=False)}\n\n"
        response = await agent.process(user_message=request.message, session_id=session_id)
        result = {
            "status": "done",
            "reply": response.reply,
            "emotion": {"type": response.emotion_result.emotion.value},
            "intent": response.semantic_result.primary_intent.value,
            "need_human": response.need_human,
            "session_id": session_id,
        }
        yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    session = await agent.session_manager.get_session(session_id)
    return {
        "session_id": session.session_id,
        "history_length": len(session.history),
        "emotion_history": session.emotion_history,
        "unresolved_count": session.unresolved_count,
        "context": session.context,
    }


@app.get("/api/stats")
async def get_stats():
    """获取运行统计"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    stats = {
        "storage_mode": agent.session_manager.mode,
        "kb_mode": agent.knowledge_base.mode,
        "llm_available": agent.config.get("llm_client") is not None,
    }
    
    # Redis 计数器
    if redis_cache and redis_cache.is_available:
        stats["total_sessions"] = await redis_cache.get_counter("sessions")
        stats["total_messages"] = await redis_cache.get_counter("messages")
    
    return stats


# ========== 路由注册 ==========
app.include_router(admin_routes.router)
app.include_router(kb_routes.router)


# ========== 异常处理器 ==========
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# ========== 安全中间件 ==========
app.add_middleware(APIKeyAuthMiddleware)

# ========== 指标中间件 ==========
app.add_middleware(MetricsMiddleware)

# ========== 静态页面挂载 ==========
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    """聊天界面"""
    return FileResponse("static/index.html")


@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """运营看板"""
    return FileResponse("static/dashboard.html")


@app.get("/admin", include_in_schema=False)
async def serve_admin():
    """运营管理控制台"""
    return FileResponse("static/admin.html")


@app.delete("/api/session/{session_id}")
async def reset_session(session_id: str):
    """重置会话（新会话按钮）"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    await agent.session_manager.delete_session(session_id)
    return {"status": "reset", "session_id": session_id}


# ========== 美妆产品搜索 ==========
@app.get("/api/products/search")
async def search_products(
    q: str = "",
    category: str = None,
    brand: str = None,
    max_price: float = None,
    skin_type: str = None,
):
    """搜索美妆产品"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    filters = {}
    if category:
        filters["category"] = category
    if brand:
        filters["brand"] = brand
    if max_price:
        filters["max_price"] = max_price

    if skin_type:
        results = agent.beauty_kb.recommend_by_skin_type(skin_type, category)
    else:
        results = agent.beauty_kb.search_products(q, filters)

    return {"total": len(results), "products": results}


@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    """获取产品详情"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    product = agent.beauty_kb.get_product_details(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@app.post("/api/products/compare")
async def compare_products(product_ids: list[str]):
    """产品对比"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.beauty_kb.compare_products(product_ids)


# ========== 肤质与成分 ==========
@app.get("/api/skin-types")
async def get_skin_types():
    """获取肤质类型列表"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return list(agent.beauty_kb.skin_types.values())


@app.get("/api/ingredients/search")
async def search_ingredients(q: str):
    """搜索成分"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.beauty_kb.search_ingredient(q)


@app.get("/api/ingredients/recommend")
async def recommend_ingredients(concern: str):
    """根据护肤需求推荐成分"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.beauty_kb.recommend_ingredients_for_concern(concern)


# ========== 大促管理 ==========
@app.get("/api/promotions")
async def get_promotions():
    """获取当前大促活动"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return {
        "active_promotions": agent.promotion_handler.active_promotions,
        "is_promotion_period": len(agent.promotion_handler.active_promotions) > 0,
    }


@app.post("/api/promotions/calculate")
async def calculate_discount(product_id: str, quantity: int = 1, promotion_id: str = None):
    """计算折扣价格"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.promotion_handler.calculate_discount(product_id, quantity, promotion_id)


@app.get("/api/promotions/scripts")
async def get_promotion_scripts(scene: str, emotion_type: str = None):
    """获取大促话术"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    script = agent.promotion_handler.get_promotion_script(scene, emotion_type)
    return {"script": script} if script else {"script": None}


# ========== 运营操作 ==========
@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    """查询订单"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    order = agent.operations_manager.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order.__dict__


@app.get("/api/logistics/{tracking_number}")
async def track_logistics(tracking_number: str):
    """物流追踪"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.operations_manager.track_logistics(tracking_number)


@app.get("/api/stock/{product_id}")
async def check_stock(product_id: str):
    """库存查询"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.operations_manager.check_stock(product_id)


@app.get("/api/price-protection/{order_id}")
async def check_price_protection(order_id: str):
    """价格保护检查"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.operations_manager.check_price_protection(order_id)


# ========== 业务数据看板 ==========
@app.get("/api/dashboard/daily")
async def get_daily_report(date: str = None):
    """获取日报表"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.metrics_dashboard.get_daily_report(date)


@app.get("/api/dashboard/period")
async def get_period_report(days: int = 7):
    """获取周期报表"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.metrics_dashboard.get_period_report(days)


@app.get("/api/dashboard/realtime")
async def get_realtime_stats():
    """获取实时统计"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.metrics_dashboard.get_realtime_stats()


@app.get("/api/dashboard/issues")
async def get_issue_distribution(days: int = 7):
    """获取问题分布"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.metrics_dashboard.get_issue_distribution(days)


# ========== 工作流管理 ==========
@app.get("/api/workflows")
async def get_workflows():
    """获取工作流列表"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return {"workflows": list(agent.workflow_engine.workflows.keys())}


@app.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, variables: dict = None):
    """执行工作流"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        execution = await agent.workflow_engine.start_execution(workflow_id, variables)
        return agent.workflow_engine.get_execution_status(execution.execution_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 问题排查链路 ==========
@app.get("/api/traces")
async def list_traces(limit: int = 50, session_id: str = None,
                      status: str = None, intent: str = None):
    """查询问答链路列表"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    traces = agent.trace_recorder.list_traces(
        limit=limit, session_id=session_id, status=status, intent=intent
    )
    return {"total": len(traces), "traces": traces}


@app.get("/api/traces/stats")
async def trace_stats():
    """链路统计"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return agent.trace_recorder.get_stats()


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    """获取单条链路详情（节点、模型IO、检索、业务查询）"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    trace = agent.trace_recorder.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@app.get("/api/unresolved")
async def list_unresolved(limit: int = 50):
    """未解决问题列表（待人工跟进）"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    items = agent.trace_recorder.list_unresolved(limit=limit)
    return {"total": len(items), "items": items}


# ========== 人工客服工作台 ==========
@app.get("/api/agents")
async def list_agents(status: str = None):
    """列出客服账号"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return {"agents": agent.human_service.list_agents(status=status)}


@app.post("/api/agents")
async def create_agent(name: str, role: str = "agent",
                       reception_scope: dict = None, max_concurrent: int = 5):
    """创建客服账号"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    a = agent.human_service.create_agent(name, role, reception_scope, max_concurrent)
    return a.to_dict()


@app.post("/api/agents/{agent_id}/status")
async def set_agent_status(agent_id: str, status: str):
    """设置客服在线状态（online/offline/busy）"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.set_agent_status(agent_id, status)


@app.post("/api/agents/{agent_id}/scope")
async def update_agent_scope(agent_id: str, scope: dict):
    """更新客服接待范围"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.update_reception_scope(agent_id, scope)


@app.get("/api/agents/{agent_id}/workload")
async def get_agent_workload(agent_id: str):
    """客服工作负载"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.get_agent_workload(agent_id)


@app.get("/api/tickets")
async def list_tickets(status: str = None, agent_id: str = None, priority: str = None):
    """列出转人工工单"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    tickets = agent.human_service.list_tickets(status=status, agent_id=agent_id, priority=priority)
    return {"total": len(tickets), "tickets": tickets}


@app.get("/api/tickets/queue")
async def get_ticket_queue():
    """待分配工单队列"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    queue = agent.human_service.get_queue()
    return {"total": len(queue), "queue": queue}


@app.get("/api/tickets/stats")
async def ticket_stats():
    """工单统计"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.get_stats()


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    """获取工单详情"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    ticket = agent.human_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket.to_dict()


@app.post("/api/tickets/{ticket_id}/assign")
async def assign_ticket(ticket_id: str, agent_id: str):
    """分配工单给客服"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.assign_to_agent(ticket_id, agent_id)


@app.post("/api/sessions/{session_id}/takeover")
async def takeover_session(session_id: str, agent_id: str):
    """客服接管会话"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.takeover(agent_id, session_id)


@app.post("/api/sessions/{session_id}/agent-reply")
async def agent_reply(session_id: str, agent_id: str, content: str):
    """客服回复会话"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.agent_reply(agent_id, session_id, content)


@app.post("/api/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str, resolution: str = ""):
    """关闭工单"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.human_service.close_ticket(ticket_id, resolution)


# ========== 入口 ==========
if __name__ == "__main__":
    import uvicorn
    config = load_config()
    uvicorn.run(
        "src.main:app",
        host=str(config["app"]["host"]),
        port=int(config["app"]["port"]),
        reload=False,
    )
