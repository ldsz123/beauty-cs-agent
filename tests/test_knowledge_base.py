"""
知识库模块测试
"""
import pytest
from src.modules.knowledge_base import KnowledgeBase, SearchResult


class TestKnowledgeBase:
    """知识库测试"""

    @pytest.fixture
    def kb(self):
        return KnowledgeBase(config={"top_k": 5, "cache_ttl": 300}, mode="builtin")

    @pytest.mark.asyncio
    async def test_search_builtin(self, kb):
        """测试内置知识库检索"""
        result = await kb.search("怎么退货退款？")

        assert result != ""
        assert "退货" in result

    @pytest.mark.asyncio
    async def test_search_shipping(self, kb):
        """测试物流相关检索"""
        result = await kb.search("运费怎么算？满多少包邮？")

        assert result != ""
        assert "物流" in result or "运费" in result

    @pytest.mark.asyncio
    async def test_search_no_match(self, kb):
        """测试无匹配结果"""
        result = await kb.search("zzzxxxccc")

        assert result == ""

    @pytest.mark.asyncio
    async def test_search_with_intent(self, kb):
        """测试带意图的检索"""
        from src.layers.semantic_layer import IntentType

        result = await kb.search(
            "我要退货",
            intent=IntentType.RETURN_REFUND,
        )

        assert result != ""
        assert "退货" in result

    @pytest.mark.asyncio
    async def test_add_entry(self, kb):
        """测试添加知识库条目"""
        await kb.add_entry(
            category="测试分类",
            content="测试内容",
            tags=["测试"],
        )

        result = await kb.search("测试内容")
        assert "测试内容" in result

    def test_extract_keywords(self, kb):
        """测试关键词提取"""
        keywords = kb._extract_keywords("怎么退货退款？运费怎么算？")

        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_extract_keywords_fallback(self, kb):
        """测试关键词提取 fallback"""
        # 测试无 jieba 时的 fallback
        keywords = kb._extract_keywords("退货退款")

        assert isinstance(keywords, list)
