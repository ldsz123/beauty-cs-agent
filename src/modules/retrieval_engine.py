"""
检索增强引擎
混合检索（关键词 + 向量）+ 重排 + 来源追溯
"""
import math
import hashlib
import re
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class RetrievedChunk:
    """检索到的知识片段"""
    chunk_id: str
    content: str
    category: str = ""
    title: str = ""
    tags: list = field(default_factory=list)
    keyword_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    matched_by: list = field(default_factory=list)  # ["keyword", "vector"]

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "category": self.category,
            "title": self.title,
            "tags": self.tags,
            "scores": {
                "keyword": round(self.keyword_score, 4),
                "vector": round(self.vector_score, 4),
                "rerank": round(self.rerank_score, 4),
                "final": round(self.final_score, 4),
            },
            "matched_by": self.matched_by,
        }


@dataclass
class RetrievalResult:
    """检索结果"""
    query: str
    chunks: list = field(default_factory=list)
    total_candidates: int = 0
    strategy: str = "hybrid"

    def to_context(self, max_chunks: int = 3, max_chars_per_chunk: int = 180) -> str:
        """转换为 LLM 上下文（截断以控制 prompt 长度、降低延迟）"""
        if not self.chunks:
            return ""
        parts = []
        for c in self.chunks[:max_chunks]:
            text = c.content
            if len(text) > max_chars_per_chunk:
                text = text[:max_chars_per_chunk] + "…"
            parts.append(f"[{c.category}] {text}")
        return "\n\n".join(parts)

    def to_sources(self, max_chunks: int = 5) -> list:
        """转换为来源列表（用于前端展示）"""
        return [
            {
                "chunk_id": c.chunk_id,
                "title": c.title or c.category,
                "category": c.category,
                "content": c.content[:200] + ("..." if len(c.content) > 200 else ""),
                "score": round(c.final_score, 4),
                "matched_by": c.matched_by,
            }
            for c in self.chunks[:max_chunks]
        ]


class LocalEmbedder:
    """
    本地哈希向量化器（无需外部 API）
    使用字符 n-gram 哈希投影到固定维度，保证确定性
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        """文本 -> 向量"""
        vec = [0.0] * self.dim
        if not text:
            return vec

        # 字符级 2-gram + 3-gram
        text = text.lower()
        grams = []
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                grams.append(text[i:i + n])

        if not grams:
            grams = [text]

        for gram in grams:
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h // self.dim) % 2 == 0 else -1.0
            vec[idx] += sign

        return self._normalize(vec)

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


class RetrievalEngine:
    """
    混合检索 + 重排引擎
    1. 关键词检索（召回）
    2. 向量检索（召回）
    3. RRF 融合
    4. 重排（启发式 + 可选 LLM）
    """

    def __init__(self, knowledge_base, llm_client=None, embedder=None):
        self.kb = knowledge_base
        self.llm = llm_client
        self.embedder = embedder or LocalEmbedder(dim=256)
        self._chunk_vectors: dict = {}  # chunk_id -> vector
        self._indexed = False
        logger.info("RetrievalEngine initialized")

    # ========== 索引构建 ==========
    def build_index(self):
        """构建向量索引"""
        chunks = self.kb.get_all_chunks()
        self._chunk_vectors = {}
        for chunk in chunks:
            text = f"{chunk.get('title', '')} {chunk.get('content', '')} {' '.join(chunk.get('tags', []))}"
            self._chunk_vectors[chunk["chunk_id"]] = self.embedder.embed(text)
        self._indexed = True
        logger.info(f"Vector index built: {len(self._chunk_vectors)} chunks")

    def _ensure_index(self):
        if not self._indexed:
            self.build_index()

    # ========== 关键词检索 ==========
    def _keyword_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """关键词召回"""
        chunks = self.kb.get_all_chunks()
        query_lower = query.lower()
        query_keywords = self._extract_keywords(query)
        results = []

        for chunk in chunks:
            score = 0.0
            content = chunk.get("content", "")
            title = chunk.get("title", "")
            tags = chunk.get("tags", [])

            # 标签命中
            for tag in tags:
                if tag and tag in query:
                    score += 2.0
            # 关键词命中
            for kw in query_keywords:
                if kw in title:
                    score += 1.5
                if kw in content:
                    score += 1.0
            # 短语命中
            if len(query_lower) >= 4 and query_lower in content.lower():
                score += 3.0

            if score > 0:
                rc = RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    content=content,
                    category=chunk.get("category", ""),
                    title=title,
                    tags=tags,
                    keyword_score=score,
                    matched_by=["keyword"],
                )
                results.append(rc)

        results.sort(key=lambda x: x.keyword_score, reverse=True)
        return results[:top_k * 2]

    def _extract_keywords(self, query: str) -> list[str]:
        """提取查询关键词"""
        try:
            import jieba.analyse
            kws = jieba.analyse.extract_tags(query, topK=8)
            return [k for k in kws if len(k) >= 2]
        except ImportError:
            return [w for w in re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{3,}", query)]

    # ========== 向量检索 ==========
    def _vector_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """向量召回"""
        self._ensure_index()
        query_vec = self.embedder.embed(query)
        chunks_map = {c["chunk_id"]: c for c in self.kb.get_all_chunks()}
        results = []

        for chunk_id, vec in self._chunk_vectors.items():
            sim = cosine_similarity(query_vec, vec)
            if sim > 0.05:  # 相似度阈值
                chunk = chunks_map.get(chunk_id)
                if not chunk:
                    continue
                rc = RetrievedChunk(
                    chunk_id=chunk_id,
                    content=chunk.get("content", ""),
                    category=chunk.get("category", ""),
                    title=chunk.get("title", ""),
                    tags=chunk.get("tags", []),
                    vector_score=sim,
                    matched_by=["vector"],
                )
                results.append(rc)

        results.sort(key=lambda x: x.vector_score, reverse=True)
        return results[:top_k * 2]

    # ========== RRF 融合 ==========
    def _rrf_fuse(self, keyword_results: list[RetrievedChunk],
                  vector_results: list[RetrievedChunk],
                  k: int = 60) -> list[RetrievedChunk]:
        """Reciprocal Rank Fusion 融合两路召回"""
        merged: dict[str, RetrievedChunk] = {}
        rrf_scores: dict[str, float] = {}

        for rank, rc in enumerate(keyword_results):
            merged[rc.chunk_id] = rc
            rrf_scores[rc.chunk_id] = rrf_scores.get(rc.chunk_id, 0) + 1.0 / (k + rank + 1)

        for rank, rc in enumerate(vector_results):
            if rc.chunk_id in merged:
                merged[rc.chunk_id].vector_score = rc.vector_score
                if "vector" not in merged[rc.chunk_id].matched_by:
                    merged[rc.chunk_id].matched_by.append("vector")
            else:
                merged[rc.chunk_id] = rc
            rrf_scores[rc.chunk_id] = rrf_scores.get(rc.chunk_id, 0) + 1.0 / (k + rank + 1)

        for chunk_id, rc in merged.items():
            rc.final_score = rrf_scores.get(chunk_id, 0.0)

        return sorted(merged.values(), key=lambda x: x.final_score, reverse=True)

    # ========== 重排 ==========
    def _rerank(self, query: str, candidates: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        """
        重排：启发式打分
        - 关键词覆盖率
        - 向量相似度
        - 内容长度惩罚（过短/过长降权）
        - 类别与查询的语义接近度
        """
        query_keywords = set(self._extract_keywords(query))
        query_lower = query.lower()

        for rc in candidates:
            content_lower = rc.content.lower()

            # 1. 关键词覆盖率
            if query_keywords:
                covered = sum(1 for kw in query_keywords if kw in content_lower)
                coverage = covered / len(query_keywords)
            else:
                coverage = 0.0

            # 2. 向量相似度（归一化到 0-1）
            vector_norm = (rc.vector_score + 1) / 2

            # 3. 长度合理性（80-500 字最佳）
            length = len(rc.content)
            if 80 <= length <= 500:
                length_factor = 1.0
            elif length < 80:
                length_factor = 0.7
            else:
                length_factor = 0.85

            # 4. 标题命中加权
            title_bonus = 0.15 if rc.title and rc.title.lower() in query_lower else 0.0

            rerank_score = (
                coverage * 0.5 +
                vector_norm * 0.3 +
                length_factor * 0.2 +
                title_bonus
            )
            rc.rerank_score = rerank_score

            # 最终分：RRF 归一化 + 重排分
            rc.final_score = rc.final_score * 0.3 + rerank_score * 0.7

        candidates.sort(key=lambda x: x.final_score, reverse=True)
        return candidates[:top_k]

    # ========== 主入口 ==========
    async def retrieve(self, query: str, intent=None, entities=None,
                       top_k: int = 5) -> RetrievalResult:
        """混合检索主流程"""
        if not query or not query.strip():
            return RetrievalResult(query=query, chunks=[], strategy="empty")

        # 1. 双路召回
        keyword_results = self._keyword_search(query, top_k)
        vector_results = self._vector_search(query, top_k)

        total = len({r.chunk_id for r in keyword_results} | {r.chunk_id for r in vector_results})

        # 2. 融合
        fused = self._rrf_fuse(keyword_results, vector_results)

        # 3. 重排
        reranked = self._rerank(query, fused, top_k)

        return RetrievalResult(
            query=query,
            chunks=reranked,
            total_candidates=total,
            strategy="hybrid",
        )
