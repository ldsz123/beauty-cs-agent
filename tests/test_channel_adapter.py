"""
多渠道接入模块测试
"""
import pytest
import json
from src.modules.channel_adapter import ChannelAdapter, ChannelMessage, ChannelResponse


class TestChannelAdapter:
    """多渠道适配器测试"""

    @pytest.fixture
    def adapter(self):
        return ChannelAdapter()

    def test_initialization(self, adapter):
        """测试初始化"""
        assert adapter.channels == {}
        assert adapter.message_handlers == []

    def test_register_channel(self, adapter):
        """测试注册渠道"""
        adapter.register_channel("feishu", {"app_id": "test"})
        assert "feishu" in adapter.channels

    def test_register_message_handler(self, adapter):
        """测试注册消息处理器"""
        async def handler(msg):
            return ChannelResponse(content="test")
        adapter.register_message_handler(handler)
        assert len(adapter.message_handlers) == 1

    def test_format_for_channel_text(self, adapter):
        """测试文本格式"""
        result = adapter.format_for_channel("你好", "web")
        assert result.content == "你好"
        assert result.content_type == "text"

    def test_format_for_channel_feishu(self, adapter):
        """测试飞书卡片格式"""
        result = adapter.format_for_channel("你好", "feishu")
        assert result.content_type == "card"
        card = json.loads(result.content)
        assert "elements" in card

    def test_format_for_channel_wechat(self, adapter):
        """测试微信格式"""
        result = adapter.format_for_channel("你好", "wechat")
        assert result.content_type == "text"

    def test_setup_feishu(self, adapter):
        """测试配置飞书"""
        adapter.setup_feishu("app_id", "secret", "token")
        assert adapter.feishu_handler is not None
        assert adapter.feishu_handler["app_id"] == "app_id"

    def test_verify_feishu(self, adapter):
        """测试验证飞书请求"""
        adapter.setup_feishu("app_id", "secret", "correct_token")
        assert adapter.verify_feishu("correct_token") is True
        assert adapter.verify_feishu("wrong_token") is False

    def test_verify_feishu_not_configured(self, adapter):
        """测试未配置飞书时验证"""
        assert adapter.verify_feishu("token") is False

    def test_register_webhook(self, adapter):
        """测试注册Webhook"""
        async def handler(data):
            return ChannelResponse(content="ok")
        adapter.register_webhook("webhook_1", "secret", handler)
        assert "webhook_1" in adapter.webhook_handlers

    def test_verify_webhook(self, adapter):
        """测试验证Webhook签名"""
        async def handler(data):
            return ChannelResponse(content="ok")
        adapter.register_webhook("webhook_1", "secret_key", handler)

        import hmac, hashlib
        body = '{"test": "data"}'
        sig = hmac.new("secret_key".encode(), body.encode(), hashlib.sha256).hexdigest()
        assert adapter.verify_webhook("webhook_1", sig, body) is True
        assert adapter.verify_webhook("webhook_1", "wrong_sig", body) is False

    def test_generate_api_key(self, adapter):
        """测试生成API Key"""
        key = adapter.generate_api_key("test_app")
        assert key.startswith("ak_")
        assert len(key) > 10

    def test_validate_api_key(self, adapter):
        """测试验证API Key"""
        assert adapter.validate_api_key("ak_test123") is True
        assert adapter.validate_api_key("invalid") is False
