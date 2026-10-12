"""
检索增强引擎测试
"""
import pytest
from src.modules.knowledge_base import KnowledgeBase
from src.modules.retrieval_engine import (
    RetrievalEngine, LocalEmbedder, cosine_similarity, RetrievedChunk, RetrievalResult
)


class TestLocalEmbedder:
    """本地向量化器测试"""

    def test_embed_deterministic(self):
        """测试向量化确定性"""
        embedder = LocalEmbedder(dim=256)
        v1 = embedder.embed("退货退款政策")
        v2 = embedder.embed("退货退款政策")
        assert v1 == v2
        assert len(v1) == 256

    def test_embed_normalized(self):
        """测试向量归一化"""
        embedder = LocalEmbedder(dim=256)
        vec = embedder.embed("测试文本")
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 0.001 or norm == 0

    def test_embed_empty(self):
        """测试空文本"""
        embedder = LocalEmbedder(dim=256)
        vec = embedder.embed("")
        assert len(vec) == 256

    def test_cosine_similarity(self):
        """测试余弦相似度"""
        embedder = LocalEmbedder(dim=256)
        v1 = embedder.embed("退货退款")
        v2 = embedder.embed("退货退款政策说明")
        v3 = embedder.embed("完全不相关的内容xyz")

        sim_related = cosine_similarity(v1, v2)
        sim_unrelated = cosine_similarity(v1, v3)
        assert sim_related > sim_unrelated

    def test_cosine_similarity_edge(self):
        """测试余弦相似度边界"""
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


class TestRetrievalEngine:
    """检索引擎测试"""

    @pytest.fixture
    def engine(self):
        kb = KnowledgeBase(config={"top_k": 5}, mode="builtin")
        return RetrievalEngine(kb)

    def test_build_index(self, engine):
        """测试索引构建"""
        engine.build_index()
        assert engine._indexed is True
        assert len(engine._chunk_vectors) > 0

    @pytest.mark.asyncio
    async def test_retrieve_basic(self, engine):
        """测试基本检索"""
        result = await engine.retrieve("怎么退货退款？")
        assert isinstance(result, RetrievalResult)
        assert len(result.chunks) > 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_sources(self, engine):
        """测试返回来源"""
        result = await engine.retrieve("退货退款")
        sources = result.to_sources()
        assert len(sources) > 0
        assert "chunk_id" in sources[0]
        assert "score" in sources[0]
        assert "matched_by" in sources[0]

    @pytest.mark.asyncio
    async def test_retrieve_hybrid_matched_by(self, engine):
        """测试混合检索的命中来源"""
        result = await engine.retrieve("退货退款政策")
        # 至少有一个结果被关键词或向量命中
        all_matched = []
        for c in result.chunks:
            all_matched.extend(c.matched_by)
        assert len(all_matched) > 0

    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self, engine):
        """测试空查询"""
        result = await engine.retrieve("")
        assert result.chunks == []
        assert result.strategy == "empty"

    @pytest.mark.asyncio
    async def test_retrieve_no_match(self, engine):
        """测试无匹配"""
        result = await engine.retrieve("zzzxxxccc")
        assert result.strategy == "hybrid"

    @pytest.mark.asyncio
    async def test_to_context(self, engine):
        """测试上下文转换"""
        result = await engine.retrieve("退货退款")
        context = result.to_context()
        assert len(context) > 0

    @pytest.mark.asyncio
    async def test_rerank_ordering(self, engine):
        """测试重排后分数递减"""
        result = await engine.retrieve("退货退款")
        if len(result.chunks) >= 2:
            assert result.chunks[0].final_score >= result.chunks[1].final_score

    @pytest.mark.asyncio
    async def test_top_k_limit(self, engine):
        """测试 top_k 限制"""
        result = await engine.retrieve("退货 物流 支付 发票", top_k=2)
        assert len(result.chunks) <= 2
