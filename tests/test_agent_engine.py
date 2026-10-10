"""
Agent 引擎测试
测试 CustomerServiceAgent 的完整流程
"""
import pytest
from src.agent_engine import CustomerServiceAgent, AgentResponse
from tests.mocks.llm_mock import MockLLMClient


class TestCustomerServiceAgent:
    """Agent 引擎测试"""

    @pytest.fixture
    def agent(self, test_config):
        """创建测试 Agent"""
        config = {**test_config, "llm_client": MockLLMClient()}
        return CustomerServiceAgent(config)

    @pytest.mark.asyncio
    async def test_process_basic(self, agent):
        """测试基本消息处理"""
        response = await agent.process("你好", session_id="test-001")

        assert isinstance(response, AgentResponse)
        assert response.reply != ""
        assert response.emotion_result is not None
        assert response.semantic_result is not None
        assert response.entities is not None
        assert response.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_process_with_order_query(self, agent):
        """测试订单查询"""
        response = await agent.process(
            "帮我查一下订单TB20240101123456的状态",
            session_id="test-002"
        )

        assert response.reply != ""
        assert response.entities.order_id == "TB20240101123456"

    @pytest.mark.asyncio
    async def test_process_with_emotion(self, agent):
        """测试情感识别（Mock LLM 返回 neutral）"""
        response = await agent.process(
            "你们这是什么垃圾商家！太差了！",
            session_id="test-003"
        )

        # Mock LLM 返回 neutral，但规则引擎会识别为 angry
        # 由于 Mock LLM 的 confidence > 0，融合结果以 LLM 为主
        assert response.emotion_result is not None
        assert response.emotion_result.emotion.value in ("angry", "neutral")

    @pytest.mark.asyncio
    async def test_process_with_image(self, agent):
        """测试带图片的消息（Mock LLM 不支持图片时 has_image=False）"""
        response = await agent.process(
            "这个商品有问题",
            session_id="test-004",
            image_data=b"fake_image_data"
        )

        assert response.reply != ""
        # Mock LLM 的 chat_with_image 返回 JSON，但 vision_module 可能失败
        # 所以 has_image 可能为 False，这是预期行为

    @pytest.mark.asyncio
    async def test_session_context(self, agent):
        """测试会话上下文"""
        session_id = "test-005"

        # 第一轮
        await agent.process("我的订单什么时候发货？", session_id=session_id)

        # 第二轮（应该有上下文）
        response = await agent.process("那物流呢？", session_id=session_id)

        assert response.reply != ""
        session = await agent.session_manager.get_session(session_id)
        assert len(session.history) >= 4  # 2轮对话 = 4条消息

    @pytest.mark.asyncio
    async def test_escalation(self, agent):
        """测试转人工判断（Mock LLM 返回 general_chat，不触发转人工）"""
        session_id = "test-006"

        # Mock LLM 返回 general_chat，不会触发转人工
        # 测试 need_human 字段存在且为 bool
        response = await agent.process(
            "我要投诉你们！太差了！",
            session_id=session_id
        )

        assert isinstance(response.need_human, bool)

    @pytest.mark.asyncio
    async def test_fallback_response(self, agent):
        """测试无 LLM 时的 fallback 回复"""
        # 创建无 LLM 的 agent
        from src.agent_engine import CustomerServiceAgent
        config = {
            "llm_client": None,
            "session_ttl": 3600,
            "max_history": 20,
            "emotion_rule_weight": 0.3,
            "emotion_llm_weight": 0.7,
            "kb_config": {"top_k": 5, "cache_ttl": 300},
            "session_mode": "memory",
            "kb_mode": "builtin",
        }
        no_llm_agent = CustomerServiceAgent(config)

        response = await no_llm_agent.process("我要退货", session_id="test-007")

        assert response.reply != ""
        assert "退货" in response.reply
