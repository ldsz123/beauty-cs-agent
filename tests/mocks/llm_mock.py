"""
Mock LLM 客户端
用于测试，返回预设的 JSON 响应
"""
import json
from typing import Optional, AsyncGenerator


class MockLLMClient:
    """Mock LLM 客户端"""

    def __init__(self):
        self.call_count = 0
        self.last_prompt = None

    async def chat(self, prompt: str,
                   system_prompt: str = None,
                   response_format: str = "text",
                   temperature: float = 0.7,
                   max_tokens: int = 2048):
        """模拟 LLM 对话"""
        self.call_count += 1
        self.last_prompt = prompt

        # 合并分析（单次调用返回情感+意图+实体）
        if "一次性分析" in prompt or "电商客服分析专家" in prompt:
            return {
                "emotion": {"type": "neutral", "intensity": 1, "confidence": 0.8},
                "intent": {"primary": "general_chat", "confidence": 0.85, "urgency": "low"},
                "entities": {
                    "order_id": None, "tracking_number": None, "product_name": None,
                    "phone": None, "amount": None, "quantity": None, "issue_type": None,
                },
            }

        # 根据 prompt 内容返回不同的响应
        if "情感分析" in prompt or "情感状态" in prompt:
            return {
                "emotion": "neutral",
                "intensity": 1,
                "confidence": 0.8,
                "triggers": [],
                "need_human": False,
            }
        elif "意图识别" in prompt or "意图" in prompt:
            return {
                "primary_intent": "general_chat",
                "secondary_intents": [],
                "confidence": 0.9,
                "urgency": "low",
                "context_dependencies": [],
                "required_info": [],
                "reasoning": "Mock classification",
            }
        elif "实体提取" in prompt:
            return {
                "order_id": None,
                "tracking_number": None,
                "product_name": None,
                "phone": None,
                "amount": None,
                "quantity": None,
                "issue_type": None,
                "issue_description": None,
            }
        elif "电商客服助手" in prompt:
            return "您好，感谢您的咨询。请问有什么可以帮您的？"
        else:
            return "Mock response"

    async def chat_stream(self, prompt: str, system_prompt: str = None) -> AsyncGenerator[str, None]:
        """模拟流式对话"""
        yield "Mock "
        yield "streaming "
        yield "response"

    async def chat_with_image(self, prompt: str, image_data: bytes, response_format: str = "text") -> str:
        """模拟图片理解"""
        return json.dumps({
            "image_type": "unknown",
            "description": "Mock image description",
            "extracted_text": "",
            "relevant_info": {},
            "confidence": 0.5,
        })

    async def embed(self, text: str) -> list[float]:
        """模拟文本嵌入"""
        return [0.0] * 1536

    async def close(self):
        """关闭客户端"""
        pass
