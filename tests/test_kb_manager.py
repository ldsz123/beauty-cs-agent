"""
知识库管理测试
"""
import pytest
import time
from src.modules.kb_manager import KBManager, Document, Chunk, KBVersion
from src.modules.knowledge_base import KnowledgeBase


@pytest.fixture
def kbm():
    kb = KnowledgeBase(config={"top_k": 5}, mode="builtin")
    return KBManager(knowledge_base=kb, chunk_size=100, chunk_overlap=20)


class TestDocumentManagement:
    """文档管理测试"""

    def test_seed_documents(self, kbm):
        docs = kbm.list_documents()
        assert len(docs) > 0

    def test_create_document(self, kbm):
        doc = kbm.create_document("退货政策", "商品签收后7天内可退货。需要保持商品完好。",
                                  category="退货", tags=["退货", "政策"])
        assert doc.doc_id.startswith("doc_")
        assert kbm.get_document(doc.doc_id) is not None

    def test_create_document_auto_chunking(self, kbm):
        doc = kbm.create_document("长文档", "第一句。" * 50, category="测试")
        chunks = kbm.list_chunks(doc.doc_id)
        assert len(chunks) > 1  # 应被切成多个切片

    def test_list_documents_filter(self, kbm):
        kbm.create_document("测试A", "内容", category="分类A")
        docs = kbm.list_documents(category="分类A")
        assert all(d["category"] == "分类A" for d in docs)

    def test_get_document_with_chunks(self, kbm):
        doc = kbm.create_document("测试", "内容一。内容二。", category="测试")
        result = kbm.get_document(doc.doc_id, with_chunks=True)
        assert "chunks" in result
        assert len(result["chunks"]) > 0

    def test_update_document(self, kbm):
        doc = kbm.create_document("原标题", "原内容")
        result = kbm.update_document(doc.doc_id, {"title": "新标题"})
        assert result["title"] == "新标题"

    def test_update_document_rechunk(self, kbm):
        doc = kbm.create_document("测试", "短内容")
        old_chunks = len(kbm.list_chunks(doc.doc_id))
        # 更新为长内容，应重新切片
        kbm.update_document(doc.doc_id, {"content": "新句子。" * 50})
        new_chunks = len(kbm.list_chunks(doc.doc_id))
        assert new_chunks >= old_chunks

    def test_delete_document(self, kbm):
        doc = kbm.create_document("待删", "内容")
        result = kbm.delete_document(doc.doc_id)
        assert result["status"] == "deleted"
        assert kbm.get_document(doc.doc_id) is None
        # 切片也应删除
        assert len(kbm.list_chunks(doc.doc_id)) == 0


class TestChunkManagement:
    """切片管理测试"""

    def test_split_text(self, kbm):
        text = "第一句。第二句。第三句。第四句。"
        chunks = kbm.split_text(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, str) for c in chunks)

    def test_split_empty(self, kbm):
        assert kbm.split_text("") == []

    def test_list_chunks(self, kbm):
        doc = kbm.create_document("测试", "内容一。内容二。")
        chunks = kbm.list_chunks(doc.doc_id)
        assert len(chunks) > 0

    def test_update_chunk(self, kbm):
        doc = kbm.create_document("测试", "原内容")
        chunk_id = kbm.list_chunks(doc.doc_id)[0]["chunk_id"]
        result = kbm.update_chunk(chunk_id, "修改后的内容")
        assert result["content"] == "修改后的内容"
        # 内容变化应清空向量
        assert result["vectorized"] is False

    def test_update_chunk_not_found(self, kbm):
        assert "error" in kbm.update_chunk("nonexistent", "内容")

    def test_add_chunk(self, kbm):
        doc = kbm.create_document("测试", "原内容")
        result = kbm.add_chunk(doc.doc_id, "新增切片内容")
        assert "chunk_id" in result
        assert len(kbm.list_chunks(doc.doc_id)) == 2

    def test_delete_chunk(self, kbm):
        doc = kbm.create_document("测试", "内容")
        chunk_id = kbm.list_chunks(doc.doc_id)[0]["chunk_id"]
        result = kbm.delete_chunk(chunk_id)
        assert result["status"] == "deleted"

    def test_toggle_chunk(self, kbm):
        doc = kbm.create_document("测试", "内容")
        chunk_id = kbm.list_chunks(doc.doc_id)[0]["chunk_id"]
        result = kbm.toggle_chunk(chunk_id, False)
        assert result["enabled"] is False


class TestVectorization:
    """向量化测试"""

    def test_vectorize_chunk(self, kbm):
        doc = kbm.create_document("测试", "需要向量化的内容")
        chunk_id = kbm.list_chunks(doc.doc_id)[0]["chunk_id"]
        result = kbm.vectorize_chunk(chunk_id)
        assert result["vectorized"] is True

    def test_vectorize_all(self, kbm):
        result = kbm.vectorize_all()
        assert result["vectorized"] > 0
        assert result["vectorized"] == result["total"]

    def test_get_chunk_with_embedding(self, kbm):
        doc = kbm.create_document("测试", "内容")
        chunk_id = kbm.list_chunks(doc.doc_id)[0]["chunk_id"]
        kbm.vectorize_chunk(chunk_id)
        chunk = kbm.get_chunk(chunk_id)
        assert len(chunk["embedding"]) > 0


class TestVersionManagement:
    """版本管理测试"""

    def test_initial_version(self, kbm):
        versions = kbm.list_versions()
        assert len(versions) >= 1
        assert versions[0]["status"] == "published"

    def test_create_version(self, kbm):
        v = kbm.create_version("v2", note="测试版本")
        assert v.version_id.startswith("ver_")
        assert v.status == "draft"

    def test_publish_version(self, kbm):
        v = kbm.create_version("v2")
        result = kbm.publish_version(v.version_id)
        assert result["status"] == "published"

    def test_publish_archives_old(self, kbm):
        v1 = kbm.create_version("v2")
        kbm.publish_version(v1.version_id)
        versions = {x["version_id"]: x for x in kbm.list_versions()}
        published = [x for x in versions.values() if x["status"] == "published"]
        assert len(published) == 1

    def test_publish_twice_fails(self, kbm):
        v = kbm.create_version("v2")
        kbm.publish_version(v.version_id)
        result = kbm.publish_version(v.version_id)
        assert "error" in result

    def test_publish_with_effective_time(self, kbm):
        v = kbm.create_version("v2")
        future = time.time() + 3600
        result = kbm.publish_version(v.version_id, effective_at=future)
        assert result["effective_at"] == future

    def test_get_version_snapshot(self, kbm):
        v = kbm.create_version("v2")
        detail = kbm.get_version(v.version_id)
        assert "chunk_snapshot" in detail
        assert "doc_snapshot" in detail

    def test_rollback(self, kbm):
        # 记录初始版本
        initial = kbm.list_versions()[-1]  # 最早的版本
        initial_chunk_count = initial["chunk_count"]

        # 添加新文档
        kbm.create_document("新文档", "新内容")
        assert len(kbm.list_chunks()) > initial_chunk_count

        # 回滚
        result = kbm.rollback_to_version(initial["version_id"])
        assert result["status"] == "rolled_back"
        assert len(kbm.list_chunks()) == initial_chunk_count

    def test_rollback_not_found(self, kbm):
        assert "error" in kbm.rollback_to_version("nonexistent")

    def test_active_chunks(self, kbm):
        chunks = kbm.get_active_chunks()
        assert len(chunks) > 0
        assert "chunk_id" in chunks[0]
        assert "content" in chunks[0]

    def test_active_chunks_excludes_disabled(self, kbm):
        v_before = kbm.create_version("before")
        kbm.publish_version(v_before.version_id)

        # 禁用所有切片
        for c in list(kbm.chunks.values()):
            c.enabled = False

        # 重新发布
        v_after = kbm.create_version("after")
        kbm.publish_version(v_after.version_id)

        chunks = kbm.get_active_chunks()
        assert len(chunks) == 0


class TestKBStats:
    """知识库统计测试"""

    def test_get_stats(self, kbm):
        stats = kbm.get_stats()
        assert stats["documents"] > 0
        assert stats["chunks"] > 0
        assert "published_version" in stats
