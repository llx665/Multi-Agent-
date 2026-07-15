from __future__ import annotations

from typing import Any, Dict

from app.services.knowledge_admin_service import knowledge_admin_service


def handle_knowledge_index_document(payload: Dict[str, Any]) -> Dict[str, Any]:
    document_id = str(payload.get("document_id") or "")
    if not document_id:
        raise ValueError("document_id is required")

    result = knowledge_admin_service.index_document(document_id)
    return {
        "document_id": document_id,
        "version_id": payload.get("version_id"),
        "chunk_count": int(result.get("chunk_count", 0) or 0),
    }


def handle_knowledge_reload(payload: Dict[str, Any]) -> Dict[str, Any]:
    del payload
    return knowledge_admin_service.reload_all_documents()


TASK_HANDLERS = {
    "knowledge_index_document": handle_knowledge_index_document,
    "knowledge_reload": handle_knowledge_reload,
}
