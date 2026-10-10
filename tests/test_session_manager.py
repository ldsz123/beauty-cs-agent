"""
会话管理器测试
测试三种模式：memory / postgres / redis
"""
import pytest
import pytest_asyncio
from src.modules.session_manager import SessionManager, Session


class TestSessionManagerMemory:
    """内存模式会话管理测试"""

    @pytest.fixture
    def manager(self):
        return SessionManager(ttl=3600, max_history=20, mode="memory")

    @pytest.mark.asyncio
    async def test_create_session(self, manager):
        """测试创建会话"""
        session = await manager.get_session("test-001")

        assert isinstance(session, Session)
        assert session.session_id == "test-001"
        assert len(session.history) == 0

    @pytest.mark.asyncio
    async def test_update_session(self, manager):
        """测试更新会话"""
        from src.layers.emotion_layer import EmotionResult, EmotionType, EmotionIntensity
        from src.layers.semantic_layer import SemanticResult, IntentType, UrgencyLevel

        emotion = EmotionResult(
            emotion=EmotionType.NEUTRAL,
            intensity=EmotionIntensity.LOW,
            confidence=0.8,
        )
        semantic = SemanticResult(
            primary_intent=IntentType.GENERAL_CHAT,
            confidence=0.9,
            urgency=UrgencyLevel.LOW,
        )

        await manager.update_session(
            "test-002",
            "你好",
            "您好，有什么可以帮您的？",
            emotion,
            semantic,
        )

        session = await manager.get_session("test-002")
        assert len(session.history) == 2
        assert session.history[0]["role"] == "user"
        assert session.history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_session_ttl(self, manager):
        """测试会话过期"""
        import time

        # 创建一个短 TTL 的 manager
        short_manager = SessionManager(ttl=1, max_history=20, mode="memory")

        await short_manager.update_session("test-003", "你好", "您好")
        session = await short_manager.get_session("test-003")
        assert len(session.history) == 2

        # 等待过期
        time.sleep(1.5)

        # 过期后应该创建新会话
        new_session = await short_manager.get_session("test-003")
        assert len(new_session.history) == 0

    @pytest.mark.asyncio
    async def test_max_history(self, manager):
        """测试最大历史消息数"""
        # 设置较小的 max_history
        small_manager = SessionManager(ttl=3600, max_history=2, mode="memory")

        for i in range(5):
            await small_manager.update_session(
                "test-004",
                f"消息{i}",
                f"回复{i}",
            )

        session = await small_manager.get_session("test-004")
        # max_history=2，最多保留 4 条消息（2轮对话）
        assert len(session.history) <= 4

    @pytest.mark.asyncio
    async def test_delete_session(self, manager):
        """测试删除会话"""
        await manager.update_session("test-005", "你好", "您好")
        session = await manager.get_session("test-005")
        assert len(session.history) == 2

        await manager.delete_session("test-005")

        # 删除后应该创建新会话
        new_session = await manager.get_session("test-005")
        assert len(new_session.history) == 0

    @pytest.mark.asyncio
    async def test_emotion_history(self, manager):
        """测试情感历史记录"""
        from src.layers.emotion_layer import EmotionResult, EmotionType, EmotionIntensity

        emotion = EmotionResult(
            emotion=EmotionType.ANGRY,
            intensity=EmotionIntensity.HIGH,
            confidence=0.9,
        )

        await manager.update_session(
            "test-006",
            "太差了！",
            "非常抱歉",
            emotion,
        )

        session = await manager.get_session("test-006")
        assert len(session.emotion_history) == 1
        assert session.emotion_history[0]["emotion"] == "angry"
