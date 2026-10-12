"""
API 端点集成测试
使用 httpx ASGITransport 测试 FastAPI 应用
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

# 测试环境强制内存模式，避免依赖数据库
os.environ["SESSION_MODE"] = "memory"
os.environ["KB_MODE"] = "builtin"
# 固定测试用 API Key
TEST_API_KEY = "test-api-key"
os.environ["API_KEYS"] = TEST_API_KEY
# 禁用真实 LLM 调用（规则模式），避免测试访问外部 API
os.environ["LLM_API_KEY"] = ""

from src.main import app


@pytest_asyncio.fixture
async def client():
    """创建测试客户端（带 lifespan + API Key，确保 Agent 初始化）"""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-API-Key": TEST_API_KEY},
        ) as ac:
            yield ac


class TestHealthEndpoints:
    """健康检查端点测试"""

    @pytest.mark.asyncio
    async def test_health(self, client):
        """测试健康检查"""
        response = await client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_ready(self, client):
        """测试 readiness 探针"""
        response = await client.get("/api/health/ready")

        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "checks" in data


class TestChatEndpoints:
    """对话端点测试"""

    @pytest.mark.asyncio
    async def test_chat_basic(self, client):
        """测试基本对话"""
        response = await client.post("/api/chat", json={
            "message": "你好",
            "session_id": "test-api-001",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] != ""
        assert "emotion" in data
        assert "intent" in data
        assert "entities" in data
        assert "processing_time_ms" in data

    @pytest.mark.asyncio
    async def test_chat_with_session(self, client):
        """测试带会话的对话"""
        session_id = "test-api-002"

        # 第一轮
        response1 = await client.post("/api/chat", json={
            "message": "我的订单什么时候发货？",
            "session_id": session_id,
        })
        assert response1.status_code == 200

        # 第二轮
        response2 = await client.post("/api/chat", json={
            "message": "那物流呢？",
            "session_id": session_id,
        })
        assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_empty_message(self, client):
        """测试空消息"""
        response = await client.post("/api/chat", json={
            "message": "",
            "session_id": "test-api-003",
        })

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_long_message(self, client):
        """测试超长消息"""
        response = await client.post("/api/chat", json={
            "message": "a" * 2001,
            "session_id": "test-api-004",
        })

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_stream(self, client):
        """测试流式对话"""
        response = await client.post("/api/chat/stream", json={
            "message": "你好",
            "session_id": "test-api-005",
        })

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")


class TestSessionEndpoints:
    """会话端点测试"""

    @pytest.mark.asyncio
    async def test_get_session(self, client):
        """测试获取会话"""
        session_id = "test-api-006"

        # 先创建会话
        await client.post("/api/chat", json={
            "message": "你好",
            "session_id": session_id,
        })

        # 获取会话
        response = await client.get(f"/api/session/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["history_length"] > 0

    @pytest.mark.asyncio
    async def test_reset_session(self, client):
        """测试重置会话"""
        session_id = "test-api-007"

        # 先创建会话
        await client.post("/api/chat", json={
            "message": "你好",
            "session_id": session_id,
        })

        # 重置会话
        response = await client.delete(f"/api/session/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset"


class TestStatsEndpoints:
    """统计端点测试"""

    @pytest.mark.asyncio
    async def test_stats(self, client):
        """测试统计信息"""
        response = await client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert "storage_mode" in data
        assert "kb_mode" in data
        assert "llm_available" in data
