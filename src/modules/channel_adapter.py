"""
多渠道接入模块
支持飞书机器人、Webhook、API开放平台
"""
import json
import time
import hmac
import hashlib
from typing import Optional, Callable
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class ChannelMessage:
    """渠道消息"""
    channel_type: str  # web/feishu/wechat/api
    user_id: str
    content: str
    message_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ChannelResponse:
    """渠道响应"""
    content: str
    content_type: str = "text"  # text/markdown/card
    extra: dict = field(default_factory=dict)


class ChannelAdapter:
    """多渠道适配器"""

    def __init__(self):
        self.channels: dict = {}  # channel_type -> channel_config
        self.message_handlers: list = []
        self.feishu_handler = None
        self.webhook_handlers: dict = {}
        logger.info("ChannelAdapter initialized")

    def register_channel(self, channel_type: str, config: dict):
        """注册渠道"""
        self.channels[channel_type] = config
        logger.info(f"Channel registered: {channel_type}")

    def register_message_handler(self, handler: Callable):
        """注册消息处理器"""
        self.message_handlers.append(handler)

    async def handle_message(self, message: ChannelMessage) -> ChannelResponse:
        """处理 incoming 消息"""
        logger.info(f"Message from {message.channel_type}: {message.content[:50]}")

        for handler in self.message_handlers:
            response = await handler(message)
            if response:
                return response

        return ChannelResponse(content="抱歉，暂时无法处理您的消息")

    def format_for_channel(self, content: str, channel_type: str) -> ChannelResponse:
        """格式化输出为渠道特定格式"""
        if channel_type == "feishu":
            return self._format_feishu(content)
        elif channel_type == "wechat":
            return self._format_wechat(content)
        else:
            return ChannelResponse(content=content)

    def _format_feishu(self, content: str) -> ChannelResponse:
        """格式化为飞书卡片消息"""
        # 飞书 interactive card
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "智能客服"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "转人工"},
                            "type": "primary",
                            "value": {"action": "escalate"},
                        }
                    ],
                },
            ],
        }
        return ChannelResponse(
            content=json.dumps(card),
            content_type="card",
            extra={"msg_type": "interactive"},
        )

    def _format_wechat(self, content: str) -> ChannelResponse:
        """格式化为微信公众号消息"""
        # 微信公众号文本消息
        return ChannelResponse(
            content=content,
            content_type="text",
            extra={"msg_type": "text"},
        )

    # ========== 飞书机器人 ==========
    def setup_feishu(self, app_id: str, app_secret: str, verification_token: str):
        """配置飞书机器人"""
        self.feishu_handler = {
            "app_id": app_id,
            "app_secret": app_secret,
            "verification_token": verification_token,
        }
        self.register_channel("feishu", {"app_id": app_id})
        logger.info("Feishu bot configured")

    def verify_feishu(self, token: str) -> bool:
        """验证飞书请求"""
        if not self.feishu_handler:
            return False
        return token == self.feishu_handler["verification_token"]

    def parse_feishu_event(self, event_data: dict) -> Optional[ChannelMessage]:
        """解析飞书事件"""
        try:
            if event_data.get("header", {}).get("event_type") != "im.message.receive_v1":
                return None

            event = event_data.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {})

            return ChannelMessage(
                channel_type="feishu",
                user_id=sender.get("sender_id", {}).get("open_id", ""),
                content=message.get("content", ""),
                message_id=message.get("message_id"),
                session_id=f"feishu_{sender.get('sender_id', {}).get('open_id', '')}",
                metadata={"chat_id": message.get("chat_id")},
            )
        except Exception as e:
            logger.error(f"Failed to parse Feishu event: {e}")
            return None

    # ========== Webhook ==========
    def register_webhook(self, webhook_id: str, secret: str, handler: Callable):
        """注册 Webhook"""
        self.webhook_handlers[webhook_id] = {
            "secret": secret,
            "handler": handler,
        }
        logger.info(f"Webhook registered: {webhook_id}")

    def verify_webhook(self, webhook_id: str, signature: str, body: str) -> bool:
        """验证 Webhook 签名"""
        webhook = self.webhook_handlers.get(webhook_id)
        if not webhook:
            return False

        expected = hmac.new(
            webhook["secret"].encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def handle_webhook(self, webhook_id: str, data: dict) -> ChannelResponse:
        """处理 Webhook 请求"""
        webhook = self.webhook_handlers.get(webhook_id)
        if not webhook:
            return ChannelResponse(content="Webhook not found")

        return await webhook["handler"](data)

    # ========== API 开放平台 ==========
    def generate_api_key(self, name: str) -> str:
        """生成 API Key"""
        key = f"ak_{hashlib.md5(f'{name}{time.time()}'.encode()).hexdigest()[:32]}"
        logger.info(f"API key generated for {name}")
        return key

    def validate_api_key(self, api_key: str) -> bool:
        """验证 API Key"""
        # TODO: 查询数据库验证
        return api_key.startswith("ak_")
