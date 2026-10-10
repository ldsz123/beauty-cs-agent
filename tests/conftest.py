"""
pytest 共享 fixtures
"""
import pytest
import pytest_asyncio
from typing import Generator

from tests.mocks.llm_mock import MockLLMClient


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """提供 Mock LLM 客户端"""
    return MockLLMClient()


@pytest.fixture
def test_config() -> dict:
    """提供测试配置"""
    return {
        "app": {"name": "test", "host": "localhost", "port": 8000},
        "llm": {
            "provider": "openai",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "timeout": 30,
        },
        "session_ttl": 3600,
        "max_history": 20,
        "emotion_rule_weight": 0.3,
        "emotion_llm_weight": 0.7,
        "kb_config": {"top_k": 5, "cache_ttl": 300},
        "session_mode": "memory",
        "kb_mode": "builtin",
        "database_url": "",
        "redis_url": "redis://localhost:6379",
    }


@pytest_asyncio.fixture
async def async_mock_llm() -> Generator[MockLLMClient, None, None]:
    """提供异步 Mock LLM 客户端"""
    client = MockLLMClient()
    yield client
    await client.close()
