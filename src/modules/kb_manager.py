"""
知识库管理模块
文档维护、切片编辑、向量化、版本发布、生效时间、历史回滚
"""
import time
import uuid
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger

from .retrieval_engine import LocalEmbedder


# ========== 文档 ==========
@dataclass
class Document:
    """知识文档"""
    doc_id: str
    title: str
    content: str
    category: str = ""
    tags: list = field(default_factory=list)
    doc_type: str = "faq"           # faq / doc
    status: str = "draft"           # draft / active / archived
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, with_content: bool = True) -> dict:
        d = {
            "doc_id": self.doc_id,
            "title": self.title,
            "category": self.category,
            "tags": self.tags,
            "doc_type": self.doc_type,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if with_content:
            d["content"] = self.content
        return d


# ========== 切片 ==========
@dataclass
class Chunk:
    """知识切片"""
    chunk_id: str
    doc_id: str
    content: str
    index: int = 0
    embedding: list = field(default_factory=list)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, with_embedding: bool = False) -> dict:
        d = {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "content": self.content,
            "index": self.index,
            "enabled": self.enabled,
            "vectorized": len(self.embedding) > 0,
            "updated_at": self.updated_at,
        }
        if with_embedding:
            d["embedding"] = self.embedding
        return d


# ========== 版本 ==========
@dataclass
class KBVersion:
    """知识库版本"""
    version_id: str
    version_number: int
    name: str
    status: str = "draft"           # draft / published / archived
    chunk_snapshot: list = field(default_factory=list)  # 快照：chunk 列表
    doc_snapshot: list = field(default_factory=list)
    effective_at: Optional[float] = None
    published_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    note: str = ""

    def to_dict(self, with_snapshot: bool = False) -> dict:
        d = {
            "version_id": self.version_id,
            "version_number": self.version_number,
            "name": self.name,
            "status": self.status,
            "chunk_count": len(self.chunk_snapshot),
            "doc_count": len(self.doc_snapshot),
            "effective_at": self.effective_at,
            "published_at": self.published_at,
            "created_at": self.created_at,
            "note": self.note,
        }
        if with_snapshot:
            d["chunk_snapshot"] = self.chunk_snapshot
            d["doc_snapshot"] = self.doc_snapshot
        return d


class KBManager:
    """
    知识库管理器
    支持文档 -> 切片 -> 向量化 -> 版本发布 -> 生效 -> 回滚
    """

    def __init__(self, knowledge_base=None, chunk_size: int = 200, chunk_overlap: int = 40):
        self.kb = knowledge_base
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedder = LocalEmbedder(dim=256)

        self.documents: dict = {}       # doc_id -> Document
        self.chunks: dict = {}          # chunk_id -> Chunk
        self.versions: dict = {}        # version_id -> KBVersion
        self._version_counter = 0
        self.active_version_id: Optional[str] = None

        self._seed_documents()
        logger.info("KBManager initialized")

    # ==================================================================
    # 初始化示例文档
    # ==================================================================
    def _seed_documents(self):
        """从现有知识库导入示例文档"""
        if not self.kb:
            return
        for i, entry in enumerate(self.kb._builtin_kb[:10]):
            doc = Document(
                doc_id=f"doc_{i:04d}",
                title=entry.get("title") or entry.get("category", f"文档{i}"),
                content=entry.get("content", ""),
                category=entry.get("category", ""),
                tags=entry.get("tags", []),
                doc_type="faq",
                status="active",
            )
            self.documents[doc.doc_id] = doc
            self._create_chunks_for_doc(doc)

        # 创建一个初始版本并发布
        if self.documents:
            v = self.create_version("初始版本", note="系统初始化")
            self.publish_version(v.version_id)

    # ==================================================================
    # 文档管理
    # ==================================================================
    def create_document(self, title: str, content: str, category: str = "",
                        tags: list = None, doc_type: str = "faq") -> Document:
        """创建文档并自动切片"""
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        doc = Document(
            doc_id=doc_id,
            title=title,
            content=content,
            category=category,
            tags=tags or [],
            doc_type=doc_type,
        )
        self.documents[doc_id] = doc
        self._create_chunks_for_doc(doc)
        logger.info(f"Document created: {doc_id} ({title})")
        return doc

    def list_documents(self, category: str = None, status: str = None) -> list:
        """文档列表"""
        docs = list(self.documents.values())
        if category:
            docs = [d for d in docs if d.category == category]
        if status:
            docs = [d for d in docs if d.status == status]
        return [d.to_dict(with_content=False) for d in docs]

    def get_document(self, doc_id: str, with_chunks: bool = False) -> Optional[dict]:
        """文档详情"""
        doc = self.documents.get(doc_id)
        if not doc:
            return None
        result = doc.to_dict()
        if with_chunks:
            result["chunks"] = [
                c.to_dict() for c in self.chunks.values() if c.doc_id == doc_id
            ]
        return result

    def update_document(self, doc_id: str, data: dict) -> dict:
        """更新文档（内容变化时重新切片）"""
        doc = self.documents.get(doc_id)
        if not doc:
            return {"error": "文档不存在"}

        content_changed = "content" in data and data["content"] != doc.content

        for key in ("title", "category", "tags", "status", "doc_type"):
            if key in data:
                setattr(doc, key, data[key])
        if "content" in data:
            doc.content = data["content"]
        doc.updated_at = time.time()

        if content_changed:
            # 删除旧切片，重新切片
            self._delete_chunks_for_doc(doc_id)
            self._create_chunks_for_doc(doc)

        return doc.to_dict()

    def delete_document(self, doc_id: str) -> dict:
        """删除文档及其切片"""
        if doc_id not in self.documents:
            return {"error": "文档不存在"}
        self._delete_chunks_for_doc(doc_id)
        self.documents.pop(doc_id)
        return {"status": "deleted", "doc_id": doc_id}

    # ==================================================================
    # 切片
    # ==================================================================
    def _create_chunks_for_doc(self, doc: Document):
        """为文档创建切片"""
        pieces = self.split_text(doc.content)
        for idx, piece in enumerate(pieces):
            chunk_id = f"ck_{doc.doc_id}_{idx}"
            chunk = Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                content=piece,
                index=idx,
            )
            self.chunks[chunk_id] = chunk

    def _delete_chunks_for_doc(self, doc_id: str):
        """删除文档的所有切片"""
        for cid in [c.chunk_id for c in self.chunks.values() if c.doc_id == doc_id]:
            self.chunks.pop(cid, None)

    def split_text(self, text: str) -> list:
        """
        文本切片
        按句子边界切分，保持 chunk_size 左右，带重叠
        """
        if not text:
            return []

        # 按标点切句
        import re
        sentences = re.split(r"(?<=[。！？；\n])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [text]

        chunks = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) <= self.chunk_size:
                current += sent
            else:
                if current:
                    chunks.append(current)
                # 重叠：保留上一段末尾
                overlap_text = current[-self.chunk_overlap:] if current else ""
                current = overlap_text + sent

        if current:
            chunks.append(current)

        return chunks or [text]

    def list_chunks(self, doc_id: str = None) -> list:
        """切片列表"""
        chunks = list(self.chunks.values())
        if doc_id:
            chunks = [c for c in chunks if c.doc_id == doc_id]
        chunks.sort(key=lambda c: (c.doc_id, c.index))
        return [c.to_dict() for c in chunks]

    def get_chunk(self, chunk_id: str) -> Optional[dict]:
        chunk = self.chunks.get(chunk_id)
        return chunk.to_dict(with_embedding=True) if chunk else None

    def update_chunk(self, chunk_id: str, content: str) -> dict:
        """编辑切片"""
        chunk = self.chunks.get(chunk_id)
        if not chunk:
            return {"error": "切片不存在"}
        chunk.content = content
        chunk.updated_at = time.time()
        # 内容变化后需重新向量化
        chunk.embedding = []
        return chunk.to_dict()

    def add_chunk(self, doc_id: str, content: str) -> dict:
        """新增切片"""
        if doc_id not in self.documents:
            return {"error": "文档不存在"}
        idx = len([c for c in self.chunks.values() if c.doc_id == doc_id])
        chunk_id = f"ck_{doc_id}_{idx}"
        chunk = Chunk(chunk_id=chunk_id, doc_id=doc_id, content=content, index=idx)
        self.chunks[chunk_id] = chunk
        return chunk.to_dict()

    def delete_chunk(self, chunk_id: str) -> dict:
        """删除切片"""
        if chunk_id not in self.chunks:
            return {"error": "切片不存在"}
        self.chunks.pop(chunk_id)
        return {"status": "deleted", "chunk_id": chunk_id}

    def toggle_chunk(self, chunk_id: str, enabled: bool) -> dict:
        """启用/禁用切片"""
        chunk = self.chunks.get(chunk_id)
        if not chunk:
            return {"error": "切片不存在"}
        chunk.enabled = enabled
        return chunk.to_dict()

    # ==================================================================
    # 向量化
    # ==================================================================
    def vectorize_chunk(self, chunk_id: str) -> dict:
        """向量化单个切片"""
        chunk = self.chunks.get(chunk_id)
        if not chunk:
            return {"error": "切片不存在"}
        chunk.embedding = self.embedder.embed(chunk.content)
        chunk.updated_at = time.time()
        return chunk.to_dict()

    def vectorize_all(self) -> dict:
        """全量向量化"""
        count = 0
        for chunk in self.chunks.values():
            chunk.embedding = self.embedder.embed(chunk.content)
            chunk.updated_at = time.time()
            count += 1
        logger.info(f"Vectorized {count} chunks")
        return {"vectorized": count, "total": len(self.chunks)}

    # ==================================================================
    # 版本管理
    # ==================================================================
    def create_version(self, name: str, note: str = "") -> KBVersion:
        """创建版本快照"""
        self._version_counter += 1
        version_id = f"ver_{uuid.uuid4().hex[:8]}"

        chunk_snapshot = [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "content": c.content,
                "index": c.index,
                "enabled": c.enabled,
                "embedding": list(c.embedding),
            }
            for c in self.chunks.values()
        ]
        doc_snapshot = [
            {"doc_id": d.doc_id, "title": d.title, "content": d.content,
             "category": d.category, "tags": d.tags, "status": d.status}
            for d in self.documents.values()
        ]

        version = KBVersion(
            version_id=version_id,
            version_number=self._version_counter,
            name=name,
            chunk_snapshot=chunk_snapshot,
            doc_snapshot=doc_snapshot,
            note=note,
        )
        self.versions[version_id] = version
        logger.info(f"Version created: {version_id} ({name})")
        return version

    def list_versions(self) -> list:
        """版本列表"""
        versions = sorted(self.versions.values(), key=lambda v: v.version_number, reverse=True)
        return [v.to_dict() for v in versions]

    def get_version(self, version_id: str) -> Optional[dict]:
        v = self.versions.get(version_id)
        return v.to_dict(with_snapshot=True) if v else None

    def publish_version(self, version_id: str, effective_at: float = None) -> dict:
        """发布版本（可设置生效时间）"""
        version = self.versions.get(version_id)
        if not version:
            return {"error": "版本不存在"}
        if version.status == "published":
            return {"error": "版本已发布"}

        # 归档旧的已发布版本
        for v in self.versions.values():
            if v.status == "published":
                v.status = "archived"

        version.status = "published"
        version.published_at = time.time()
        version.effective_at = effective_at if effective_at is not None else time.time()
        self.active_version_id = version_id

        logger.info(f"Version published: {version_id} (effective_at={version.effective_at})")
        return version.to_dict()

    def rollback_to_version(self, version_id: str) -> dict:
        """回滚到指定版本"""
        version = self.versions.get(version_id)
        if not version:
            return {"error": "版本不存在"}

        # 用快照恢复切片
        self.chunks = {}
        for cs in version.chunk_snapshot:
            self.chunks[cs["chunk_id"]] = Chunk(
                chunk_id=cs["chunk_id"],
                doc_id=cs["doc_id"],
                content=cs["content"],
                index=cs["index"],
                enabled=cs.get("enabled", True),
                embedding=list(cs.get("embedding", [])),
            )

        # 恢复文档
        self.documents = {}
        for ds in version.doc_snapshot:
            self.documents[ds["doc_id"]] = Document(
                doc_id=ds["doc_id"],
                title=ds["title"],
                content=ds["content"],
                category=ds.get("category", ""),
                tags=ds.get("tags", []),
                status=ds.get("status", "active"),
            )

        # 归档其他版本，标记该版本为已发布
        for v in self.versions.values():
            if v.status == "published":
                v.status = "archived"
        version.status = "published"
        self.active_version_id = version_id

        logger.info(f"Rolled back to version: {version_id}")
        return {
            "status": "rolled_back",
            "version_id": version_id,
            "chunk_count": len(self.chunks),
            "doc_count": len(self.documents),
        }

    # ==================================================================
    # 生效切片（供检索使用）
    # ==================================================================
    def get_active_chunks(self) -> list:
        """获取当前生效的切片（已发布版本 + 已启用 + 已生效）"""
        version = self.versions.get(self.active_version_id) if self.active_version_id else None

        if version and version.status == "published":
            # 未到生效时间则用上一个版本
            if version.effective_at and version.effective_at > time.time():
                # 找上一个已归档的版本
                archived = [v for v in self.versions.values() if v.status == "archived"]
                if archived:
                    archived.sort(key=lambda v: v.version_number, reverse=True)
                    version = archived[0]

            chunks = []
            for cs in version.chunk_snapshot:
                if cs.get("enabled", True):
                    chunks.append({
                        "chunk_id": cs["chunk_id"],
                        "content": cs["content"],
                        "title": "",
                        "category": "",
                        "tags": [],
                    })
            return chunks

        # 无发布版本则返回当前启用的切片
        return [
            {
                "chunk_id": c.chunk_id,
                "content": c.content,
                "title": self.documents.get(c.doc_id, Document("", "", "")).title,
                "category": self.documents.get(c.doc_id, Document("", "", "")).category,
                "tags": self.documents.get(c.doc_id, Document("", "", "")).tags,
            }
            for c in self.chunks.values() if c.enabled
        ]

    def get_stats(self) -> dict:
        """知识库统计"""
        return {
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "enabled_chunks": sum(1 for c in self.chunks.values() if c.enabled),
            "vectorized_chunks": sum(1 for c in self.chunks.values() if c.embedding),
            "versions": len(self.versions),
            "published_version": self.active_version_id,
        }
