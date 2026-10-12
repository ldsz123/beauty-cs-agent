"""
知识库管理 API 路由
文档 / 切片 / 向量化 / 版本 / 回滚
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .state import state


router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


def _kbm():
    if not state.agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return state.agent.kb_manager


# ==================== 统计 ====================
@router.get("/stats")
async def kb_stats():
    return _kbm().get_stats()


# ==================== 文档 ====================
class DocumentIn(BaseModel):
    title: str
    content: str
    category: str = ""
    tags: list = []
    doc_type: str = "faq"


@router.get("/documents")
async def list_documents(category: str = None, status: str = None):
    return {"items": _kbm().list_documents(category, status)}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, with_chunks: bool = False):
    doc = _kbm().get_document(doc_id, with_chunks)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/documents")
async def create_document(data: DocumentIn):
    doc = _kbm().create_document(
        data.title, data.content, data.category, data.tags, data.doc_type
    )
    return doc.to_dict()


@router.put("/documents/{doc_id}")
async def update_document(doc_id: str, data: dict):
    result = _kbm().update_document(doc_id, data)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    result = _kbm().delete_document(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 切片 ====================
@router.get("/chunks")
async def list_chunks(doc_id: str = None):
    return {"items": _kbm().list_chunks(doc_id)}


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str):
    c = _kbm().get_chunk(chunk_id)
    if not c:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return c


@router.put("/chunks/{chunk_id}")
async def update_chunk(chunk_id: str, content: str):
    result = _kbm().update_chunk(chunk_id, content)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/documents/{doc_id}/chunks")
async def add_chunk(doc_id: str, content: str):
    result = _kbm().add_chunk(doc_id, content)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str):
    result = _kbm().delete_chunk(chunk_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/chunks/{chunk_id}/toggle")
async def toggle_chunk(chunk_id: str, enabled: bool):
    result = _kbm().toggle_chunk(chunk_id, enabled)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 向量化 ====================
@router.post("/chunks/{chunk_id}/vectorize")
async def vectorize_chunk(chunk_id: str):
    result = _kbm().vectorize_chunk(chunk_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/vectorize-all")
async def vectorize_all():
    return _kbm().vectorize_all()


# ==================== 版本 ====================
class VersionIn(BaseModel):
    name: str
    note: str = ""


@router.get("/versions")
async def list_versions():
    return {"items": _kbm().list_versions()}


@router.get("/versions/{version_id}")
async def get_version(version_id: str):
    v = _kbm().get_version(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return v


@router.post("/versions")
async def create_version(data: VersionIn):
    v = _kbm().create_version(data.name, data.note)
    return v.to_dict()


@router.post("/versions/{version_id}/publish")
async def publish_version(version_id: str, effective_at: float = None):
    result = _kbm().publish_version(version_id, effective_at)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/versions/{version_id}/rollback")
async def rollback_version(version_id: str):
    result = _kbm().rollback_to_version(version_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
