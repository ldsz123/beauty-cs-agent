"""
LLM 客户端封装
统一封装不同 LLM 提供商的接口
"""
from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator
import json
import time
import httpx
from loguru import logger

from ..utils.metrics import llm_calls_total, llm_call_duration_seconds, llm_tokens_total


class BaseLLMClient(ABC):
    """LLM 客户端基类"""
    
    @abstractmethod
    async def chat(self, prompt: str, 
                   system_prompt: str = None,
                   response_format: str = "text",
                   temperature: float = 0.7,
                   max_tokens: int = 2048) -> str:
        """同步对话"""
        pass
    
    @abstractmethod
    async def chat_stream(self, prompt: str,
                          system_prompt: str = None) -> AsyncGenerator[str, None]:
        """流式对话"""
        pass
    
    @abstractmethod
    async def chat_with_image(self, prompt: str,
                              image_data: bytes,
                              response_format: str = "text") -> str:
        """多模态对话（带图片）"""
        pass
    
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """文本嵌入"""
        pass

    async def close(self):
        """关闭客户端连接"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI 兼容客户端（支持 OpenAI / 通义千问 / 本地模型等）"""
    
    def __init__(self, api_key: str, base_url: str, 
                 model: str, timeout: int = 30,
                 **kwargs):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.extra_kwargs = kwargs
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
        logger.info(f"OpenAI client initialized: model={model}, base_url={base_url}")
    
    async def chat(self, prompt: str,
                   system_prompt: str = None,
                   response_format: str = "text",
                   temperature: float = 0.7,
                   max_tokens: int = 4096) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self.extra_kwargs
        }

        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        # Metrics 收集
        start_time = time.time()
        llm_calls_total.labels(provider="openai", model=self.model, call_type="chat").inc()

        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            result = response.json()

            # 记录耗时
            duration = time.time() - start_time
            llm_call_duration_seconds.labels(provider="openai", model=self.model).observe(duration)

            # 记录 token 使用量
            usage = result.get("usage", {})
            if usage:
                llm_tokens_total.labels(provider="openai", model=self.model, token_type="prompt").inc(usage.get("prompt_tokens", 0))
                llm_tokens_total.labels(provider="openai", model=self.model, token_type="completion").inc(usage.get("completion_tokens", 0))
                llm_tokens_total.labels(provider="openai", model=self.model, token_type="total").inc(usage.get("total_tokens", 0))

            message = result["choices"][0]["message"]
            content = message.get("content")

            # 思考模型（如 LongCat-2.5-Preview）可能因推理占满 token 导致 content 为空
            if content is None:
                reasoning = message.get("reasoning_content") or ""
                finish = result["choices"][0].get("finish_reason")
                if finish == "length":
                    raise ValueError(
                        f"模型输出被截断（推理占用过多 token），请增大 max_tokens。"
                        f"当前 max_tokens={max_tokens}"
                    )
                content = reasoning

            if response_format == "json":
                return json.loads(content)
            return content
        except Exception as e:
            duration = time.time() - start_time
            llm_call_duration_seconds.labels(provider="openai", model=self.model).observe(duration)
            logger.error(f"LLM chat failed: {e}")
            raise
    
    async def chat_stream(self, prompt: str,
                          system_prompt: str = None) -> AsyncGenerator[str, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7
        }
        
        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    async def chat_with_image(self, prompt: str,
                              image_data: bytes,
                              response_format: str = "text") -> str:
        import base64
        b64_image = base64.b64encode(image_data).decode()
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}"
                    }
                }
            ]
        }]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 2048,
            **self.extra_kwargs,
        }

        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        if response_format == "json":
            return json.loads(content)
        return content
    
    async def embed(self, text: str) -> list[float]:
        response = await self._client.post(
            f"{self.base_url}/embeddings",
            json={
                "model": "text-embedding-3-small",
                "input": text
            }
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    async def close(self):
        """关闭 httpx 客户端"""
        await self._client.aclose()
        logger.info("OpenAI client closed")


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude 客户端"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 timeout: int = 30, **kwargs):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
        )
    
    async def chat(self, prompt: str,
                   system_prompt: str = None,
                   response_format: str = "text",
                   temperature: float = 0.7,
                   max_tokens: int = 2048) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        if system_prompt:
            payload["system"] = system_prompt
        
        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload
        )
        response.raise_for_status()
        content = response.json()["content"][0]["text"]
        
        if response_format == "json":
            # 从回复中提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
        return content
    
    async def chat_stream(self, prompt: str, system_prompt: str = None):
        # TODO: 实现流式
        raise NotImplementedError
    
    async def chat_with_image(self, prompt: str, image_data: bytes,
                              response_format: str = "text") -> str:
        import base64
        b64 = base64.b64encode(image_data).decode()
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt}
            ]
        }]
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 2048
        }
        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]
    
    async def embed(self, text: str) -> list[float]:
        # Anthropic 不直接提供 embedding，使用 Voyage 或其他
        raise NotImplementedError


def create_llm_client(config: dict) -> BaseLLMClient:
    """工厂函数：根据配置创建 LLM 客户端"""
    provider = config.get("provider", "openai")
    # 额外请求参数（如 LongCat 的 enable_thinking）
    extra_params = config.get("extra_params", {}) or {}

    if provider == "anthropic":
        return AnthropicClient(
            api_key=config["api_key"],
            model=config.get("model", "claude-sonnet-4-20250514"),
            timeout=config.get("timeout", 30)
        )
    else:
        # 默认使用 OpenAI 兼容接口（OpenAI / LongCat / 通义 / 豆包等）
        return OpenAIClient(
            api_key=config["api_key"],
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            model=config.get("model", "gpt-4o"),
            timeout=config.get("timeout", 30),
            **extra_params,
        )
