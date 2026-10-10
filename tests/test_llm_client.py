"""
LLM 客户端测试
"""
import pytest
import pytest_asyncio
from src.models.llm_client import OpenAIClient, AnthropicClient, create_llm_client


class TestOpenAIClient:
    """OpenAI 客户端测试"""

    @pytest.fixture
    def client(self):
        return OpenAIClient(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_initialization(self, client):
        """测试初始化"""
        assert client.api_key == "test-key"
        assert client.model == "gpt-4o"
        assert client.timeout == 30

    @pytest.mark.asyncio
    async def test_close(self, client):
        """测试关闭"""
        await client.close()  # 应该不报错


class TestAnthropicClient:
    """Anthropic 客户端测试"""

    @pytest.fixture
    def client(self):
        return AnthropicClient(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
        )

    @pytest.mark.asyncio
    async def test_initialization(self, client):
        """测试初始化"""
        assert client.api_key == "test-key"
        assert client.model == "claude-sonnet-4-20250514"


class TestCreateLLMClient:
    """LLM 客户端工厂测试"""

    def test_create_openai_client(self):
        """测试创建 OpenAI 客户端"""
        config = {
            "provider": "openai",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
        }
        client = create_llm_client(config)

        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4o"

    def test_create_anthropic_client(self):
        """测试创建 Anthropic 客户端"""
        config = {
            "provider": "anthropic",
            "api_key": "test-key",
            "model": "claude-sonnet-4-20250514",
        }
        client = create_llm_client(config)

        assert isinstance(client, AnthropicClient)

    def test_create_default_client(self):
        """测试创建默认客户端（OpenAI 兼容）"""
        config = {
            "provider": "unknown",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
        }
        client = create_llm_client(config)

        assert isinstance(client, OpenAIClient)
