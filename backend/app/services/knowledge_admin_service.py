from __future__ import annotations

import hashlib
from importlib import import_module
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from config.settings import settings
from app.services.audit_log_service import AuditLogService
from app.services.rag_runtime import get_loaded_rag_tool, get_rag_tool, rag_params_manager
from app.services.task_queue_service import task_queue_service
from tools.rag.chroma_telemetry import disable_chroma_telemetry
from tools.rag.vector_store_backend import build_vector_access_metadata


ALL_KNOWLEDGE_ROLES = ["user", "operator", "admin", "super_admin"]
ALLOWED_DOC_EXTENSIONS = {".txt", ".pdf", ".docx", ".html", ".htm", ".xlsx"}
REGISTRY_VERSION = 2

_chromadb_module = None
_chromadb_settings_cls = None


def _get_chromadb_module():
    global _chromadb_module
    if _chromadb_module is None:
        _chromadb_module = import_module("chromadb")
    return _chromadb_module


def _get_chromadb_settings_cls():
    global _chromadb_settings_cls
    if _chromadb_settings_cls is None:
        _chromadb_settings_cls = import_module("chromadb.config").Settings
    return _chromadb_settings_cls


class KnowledgeConflictError(ValueError):
    pass


class KnowledgeAdminService:
    def __init__(self) -> None:
        self.reconfigure()

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[3]

    def reconfigure(
        self,
        docs_dir: Optional[str] = None,
        metadata_path: Optional[str] = None,
        audit_storage_path: Optional[str] = None,
        trash_dir: Optional[str] = None,
        history_dir: Optional[str] = None,
    ) -> None:
        project_root = self._project_root()
        self.docs_dir = Path(docs_dir) if docs_dir else project_root / "data" / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = Path(metadata_path) if metadata_path else project_root / "data" / "knowledge" / "registry.json"
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.trash_dir = Path(trash_dir) if trash_dir else self.metadata_path.parent / "trash"
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir = Path(history_dir) if history_dir else self.metadata_path.parent / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_service = AuditLogService(
            storage_path=audit_storage_path or str(project_root / "logs" / "admin_audit.jsonl")
        )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        safe = Path(filename or "").name
        if not safe or safe != (filename or "").strip():
            raise ValueError("invalid filename")
        if Path(safe).suffix.lower() not in ALLOWED_DOC_EXTENSIONS:
            raise ValueError("unsupported document type")
        return safe

    @staticmethod
    def _normalize_roles(allowed_roles: Optional[List[str]]) -> List[str]:
        if allowed_roles is None:
            return ALL_KNOWLEDGE_ROLES.copy()
        normalized = [role for role in ALL_KNOWLEDGE_ROLES if role in allowed_roles]
        if not normalized:
            return []
        return normalized

    @staticmethod
    def _normalize_tags(tags: Optional[List[str]]) -> List[str]:
        if tags is None:
            return []
        normalized = []
        seen = set()
        for tag in tags:
            value = str(tag).strip()
            if not value or value in seen:
                continue
            normalized.append(value)
            seen.add(value)
        return normalized

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _new_document_id() -> str:
        return f"doc_{uuid4().hex}"

    @staticmethod
    def _new_version_id() -> str:
        return f"ver_{uuid4().hex}"

    @staticmethod
    def _default_registry() -> Dict[str, Any]:
        return {"version": REGISTRY_VERSION, "documents": {}}

    @staticmethod
    def _default_record() -> Dict[str, Any]:
        return {
            "current_version_id": None,
            "description": "",
            "tags": [],
            "visible_to_frontend": True,
            "published": True,
            "allowed_roles": ALL_KNOWLEDGE_ROLES.copy(),
            "deleted": False,
            "created_at": None,
            "created_by": None,
            "updated_at": None,
            "updated_by": None,
            "deleted_at": None,
            "deleted_by": None,
            "chunk_count": 0,
        }

    def _compute_checksum(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        digest.update(file_path.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def _normalize_source_path(source: Optional[str]) -> str:
        value = str(source or "").strip()
        if not value:
            return ""
        try:
            return str(Path(value).expanduser().resolve(strict=False))
        except OSError:
            return str(Path(value).expanduser())

    def _get_vector_collection(self):
        try:
            rag_tool = get_loaded_rag_tool()
        except Exception:
            rag_tool = None
        collection = getattr(rag_tool, "collection", None)
        if collection is not None:
            return collection

        try:
            disable_chroma_telemetry()
            chromadb_module = _get_chromadb_module()
            settings_cls = _get_chromadb_settings_cls()
            client = chromadb_module.PersistentClient(
                path=str(self._project_root() / "chroma_data"),
                settings=settings_cls(anonymized_telemetry=False),
            )
            return client.get_collection(settings.vector_db.vector_db_collection_name)
        except Exception:
            return None

    def _chunk_counts_by_source(self) -> Dict[str, int]:
        collection = self._get_vector_collection()
        if collection is None:
            return {}
        try:
            payload = collection.get(include=["metadatas"])
        except Exception:
            return {}

        counts: Dict[str, int] = {}
        for metadata in payload.get("metadatas") or []:
            if not isinstance(metadata, dict):
                continue
            source = self._normalize_source_path(metadata.get("source_file") or metadata.get("file_path"))
            if not source:
                continue
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _history_root(self, document_id: str) -> Path:
        root = self.history_dir / document_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _manifest_path(self, document_id: str) -> Path:
        return self._history_root(document_id) / "manifest.json"

    def _default_manifest(self, document_id: str) -> Dict[str, Any]:
        return {
            "document_id": document_id,
            "current_version_id": None,
            "latest_version_no": 0,
            "versions": [],
        }

    def _load_manifest(self, document_id: str) -> Dict[str, Any]:
        manifest_path = self._manifest_path(document_id)
        if not manifest_path.exists():
            return self._default_manifest(document_id)
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeConflictError("version manifest is corrupted") from exc
        except OSError as exc:
            raise KnowledgeConflictError("version manifest is unavailable") from exc

    def _save_manifest(self, document_id: str, manifest: Dict[str, Any]) -> None:
        self._manifest_path(document_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _snapshot_file_path(self, document_id: str, version_id: str, file_type: str) -> Path:
        version_dir = self._history_root(document_id) / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir / f"source{file_type}"

    def _build_record(
        self,
        *,
        document_id: str,
        file_path: Path,
        filename: str,
        legacy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        legacy = legacy or {}
        stat = file_path.stat()
        created_at = legacy.get("created_at") or datetime.fromtimestamp(stat.st_ctime).isoformat()
        updated_at = legacy.get("updated_at") or datetime.fromtimestamp(stat.st_mtime).isoformat()
        return {
            "document_id": document_id,
            "current_version_id": legacy.get("current_version_id"),
            "filename": filename,
            "file_type": file_path.suffix.lower(),
            "storage_name": file_path.name,
            "storage_path": str(file_path.resolve()),
            "size": stat.st_size,
            "checksum": self._compute_checksum(file_path),
            "chunk_count": int(legacy.get("chunk_count", 0) or 0),
            "description": legacy.get("description", ""),
            "tags": list(legacy.get("tags", [])),
            "published": bool(legacy.get("published", True)),
            "visible_to_frontend": bool(legacy.get("visible_to_frontend", True)),
            "allowed_roles": self._normalize_roles(legacy.get("allowed_roles")),
            "deleted": bool(legacy.get("deleted", False)),
            "created_at": created_at,
            "created_by": legacy.get("created_by"),
            "updated_at": updated_at,
            "updated_by": legacy.get("updated_by"),
            "deleted_at": legacy.get("deleted_at"),
            "deleted_by": legacy.get("deleted_by"),
        }

    def _load_raw_registry(self) -> Dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_registry(self, registry: Dict[str, Any]) -> None:
        self.metadata_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize_registry(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        if raw.get("version") == REGISTRY_VERSION and isinstance(raw.get("documents"), dict):
            return raw
        return self._migrate_legacy_registry(raw)

    def _migrate_legacy_registry(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        registry = self._default_registry()
        for document_path in sorted(self.docs_dir.iterdir(), key=lambda item: item.name.lower()):
            if not document_path.is_file() or document_path.suffix.lower() not in ALLOWED_DOC_EXTENSIONS:
                continue
            legacy = raw.get(document_path.name, {}) if isinstance(raw, dict) else {}
            document_id = legacy.get("document_id") or self._new_document_id()
            registry["documents"][document_id] = self._build_record(
                document_id=document_id,
                file_path=document_path,
                filename=document_path.name,
                legacy=legacy,
            )
        self._save_registry(registry)
        return registry

    def _sync_registry_with_files(self, registry: Dict[str, Any]) -> Dict[str, Any]:
        changed = False
        documents = registry.setdefault("documents", {})
        chunk_counts = self._chunk_counts_by_source()
        by_storage_name = {
            Path(record.get("storage_name") or record.get("filename") or "").name: document_id
            for document_id, record in documents.items()
            if not record.get("deleted")
        }

        for document_path in sorted(self.docs_dir.iterdir(), key=lambda item: item.name.lower()):
            if not document_path.is_file() or document_path.suffix.lower() not in ALLOWED_DOC_EXTENSIONS:
                continue

            document_id = by_storage_name.get(document_path.name)
            if document_id:
                record = documents[document_id]
                refreshed = self._build_record(
                    document_id=document_id,
                    file_path=document_path,
                    filename=record.get("filename") or document_path.name,
                    legacy=record,
                )
                normalized_source = self._normalize_source_path(refreshed.get("storage_path") or document_path)
                if normalized_source in chunk_counts:
                    refreshed["chunk_count"] = chunk_counts[normalized_source]
                if refreshed != record:
                    documents[document_id] = refreshed
                    changed = True
                continue

            new_document_id = self._new_document_id()
            new_record = self._build_record(
                document_id=new_document_id,
                file_path=document_path,
                filename=document_path.name,
            )
            normalized_source = self._normalize_source_path(new_record.get("storage_path") or document_path)
            if normalized_source in chunk_counts:
                new_record["chunk_count"] = chunk_counts[normalized_source]
            documents[new_document_id] = new_record
            changed = True

        if changed:
            self._save_registry(registry)
        return registry

    def _load_registry(self) -> Dict[str, Any]:
        raw = self._load_raw_registry()
        registry = self._normalize_registry(raw)
        return self._sync_registry_with_files(registry)

    def _document_path(self, filename: str) -> Path:
        safe = self._safe_filename(filename)
        document_path = (self.docs_dir / safe).resolve()
        if not document_path.exists() or not document_path.is_file():
            raise FileNotFoundError(safe)
        return document_path

    def _find_document_id_by_filename(self, filename: str, registry: Dict[str, Any]) -> Optional[str]:
        safe = self._safe_filename(filename)
        for document_id, record in registry.get("documents", {}).items():
            if record.get("filename") == safe or record.get("storage_name") == safe:
                return document_id
        return None

    def _find_document_id(self, identifier: str, registry: Dict[str, Any]) -> Optional[str]:
        if identifier in registry.get("documents", {}):
            return identifier
        try:
            return self._find_document_id_by_filename(identifier, registry)
        except ValueError:
            return None

    def _record_from_filename(self, filename: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        safe = self._safe_filename(filename)
        registry = registry or self._load_registry()
        document_id = self._find_document_id_by_filename(safe, registry)
        if document_id is None:
            document_path = self._document_path(safe)
            document_id = self._new_document_id()
            registry["documents"][document_id] = self._build_record(
                document_id=document_id,
                file_path=document_path,
                filename=safe,
            )
            self._save_registry(registry)
        return registry["documents"][document_id]

    def _resolve_record(
        self,
        identifier: str,
        registry: Dict[str, Any],
        *,
        create_from_filename: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        document_id = self._find_document_id(identifier, registry)
        if document_id is not None:
            return document_id, registry["documents"][document_id]
        if create_from_filename:
            record = self._record_from_filename(identifier, registry)
            return record["document_id"], record
        raise FileNotFoundError(identifier)

    def _record_storage_path(self, record: Dict[str, Any]) -> Path:
        stored = record.get("storage_path")
        if stored:
            return Path(stored)
        storage_name = Path(record.get("storage_name") or record.get("filename") or "").name
        if not storage_name:
            raise FileNotFoundError(record.get("document_id", "document"))
        if record.get("deleted"):
            return self.trash_dir / storage_name
        return self.docs_dir / storage_name

    def _append_version_snapshot(
        self,
        *,
        record: Dict[str, Any],
        actor_id: str,
        action: str,
        reason: Optional[str] = None,
        source_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        manifest = self._load_manifest(record["document_id"])
        version_id = self._new_version_id()
        version_no = int(manifest.get("latest_version_no", 0) or 0) + 1
        snapshot_path = self._snapshot_file_path(
            record["document_id"],
            version_id,
            record.get("file_type") or Path(record["filename"]).suffix.lower(),
        )
        snapshot_path.write_bytes(self._record_storage_path(record).read_bytes())
        snapshot = {
            "version_id": version_id,
            "version_no": version_no,
            "document_id": record["document_id"],
            "action": action,
            "source_version_id": source_version_id,
            "filename": record["filename"],
            "file_type": record["file_type"],
            "snapshot_storage_name": snapshot_path.name,
            "snapshot_storage_path": str(snapshot_path.resolve()),
            "size": record["size"],
            "checksum": record["checksum"],
            "chunk_count": int(record.get("chunk_count", 0) or 0),
            "description": record.get("description", ""),
            "tags": self._normalize_tags(record.get("tags", [])),
            "created_at": self._now_iso(),
            "created_by": actor_id,
            "reason": reason,
        }
        manifest["latest_version_no"] = version_no
        manifest["current_version_id"] = version_id
        manifest.setdefault("versions", []).append(snapshot)
        self._save_manifest(record["document_id"], manifest)
        return snapshot

    def _index_file(self, file_path: Path) -> int:
        rag_tool = get_rag_tool()
        documents = rag_tool.load_document(
            str(file_path),
            chunk_size=rag_params_manager.get_chunk_size(),
            chunk_overlap=rag_params_manager.get_chunk_overlap(),
        )
        if not documents:
            return 0
        doc_ids = rag_tool.add_documents_to_vector_db(documents)
        return len(doc_ids)

    def _delete_chunks(self, source: str) -> int:
        rag_tool = get_loaded_rag_tool() or get_rag_tool()
        deleted = rag_tool.delete_documents_by_source(source)
        return int(deleted or 0)

    def get_document_access(self, filename: str) -> Dict[str, Any]:
        registry = self._load_registry()
        record = self._record_from_filename(filename, registry=registry)
        return {**self._default_record(), **record}

    def get_document(self, document_id: str, *, include_deleted: bool = True) -> Dict[str, Any]:
        registry = self._load_registry()
        _, record = self._resolve_record(document_id, registry)
        if record.get("deleted") and not include_deleted:
            raise FileNotFoundError(document_id)
        return self._serialize_record(record)

    def _serialize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **record,
            "upload_time": record.get("created_at"),
            "update_time": record.get("updated_at"),
        }

    def list_documents(
        self,
        *,
        keyword: Optional[str] = None,
        status: str = "active",
        published: Optional[bool] = None,
        visible_to_frontend: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        registry = self._load_registry()
        documents = list(registry.get("documents", {}).values())

        if status == "active":
            documents = [document for document in documents if not document.get("deleted")]
        elif status == "deleted":
            documents = [document for document in documents if document.get("deleted")]
        elif status != "all":
            raise ValueError("invalid status")

        if published is not None:
            documents = [document for document in documents if document.get("published") is published]

        if visible_to_frontend is not None:
            documents = [
                document for document in documents if document.get("visible_to_frontend") is visible_to_frontend
            ]

        if keyword:
            needle = keyword.strip().lower()
            documents = [
                document
                for document in documents
                if needle in str(document.get("filename", "")).lower()
                or needle in str(document.get("description", "")).lower()
                or any(needle in str(tag).lower() for tag in document.get("tags", []))
            ]

        documents.sort(key=lambda item: str(item.get("filename", "")).lower())
        return [self._serialize_record(document) for document in documents]

    @staticmethod
    def can_role_access(record: Dict[str, Any], role: str) -> bool:
        return bool(
            not record.get("deleted")
            and record.get("visible_to_frontend")
            and record.get("published")
            and role in record.get("allowed_roles", [])
        )

    def can_user_access_document(self, filename: str, role: str) -> bool:
        return self.can_role_access(self.get_document_access(filename), role)

    def get_access_policy_version(self) -> str:
        registry = self._load_registry()
        policy_payload = [
            {
                "document_id": document_id,
                "storage_path": self._normalize_source_path(record.get("storage_path")),
                "published": bool(record.get("published")),
                "visible_to_frontend": bool(record.get("visible_to_frontend")),
                "allowed_roles": self._normalize_roles(record.get("allowed_roles")),
                "deleted": bool(record.get("deleted")),
                "checksum": record.get("checksum", ""),
            }
            for document_id, record in sorted(registry.get("documents", {}).items())
        ]
        encoded = json.dumps(policy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def filter_retrieved_documents_for_role(self, documents: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        if not documents:
            return []

        registry = self._load_registry()
        records_by_source = {}
        for record in registry.get("documents", {}).values():
            storage_path = self._normalize_source_path(record.get("storage_path"))
            if storage_path:
                records_by_source[storage_path] = record
            filename = Path(record.get("storage_name") or record.get("filename") or "").name
            if filename:
                records_by_source[filename] = record

        filtered: List[Dict[str, Any]] = []
        for document in documents:
            source = (
                document.get("source_file")
                or document.get("metadata", {}).get("source_file")
                or document.get("metadata", {}).get("file_path")
            )
            source_key = self._normalize_source_path(source)
            filename_key = Path(str(source or "")).name
            record = records_by_source.get(source_key) or records_by_source.get(filename_key)
            if not record or not self.can_role_access(record, role):
                continue

            document_copy = dict(document)
            metadata = dict(document_copy.get("metadata") or {})
            metadata["access_policy"] = {
                "document_id": record.get("document_id"),
                "published": bool(record.get("published")),
                "visible_to_frontend": bool(record.get("visible_to_frontend")),
                "allowed_roles": self._normalize_roles(record.get("allowed_roles")),
            }
            document_copy["metadata"] = metadata
            filtered.append(document_copy)

        return filtered

    def get_vector_access_metadata_for_source(self, source: str, tenant_id: str = "default") -> Dict[str, Any]:
        registry = self._load_registry()
        record = self._find_record_by_source(source, registry)
        return build_vector_access_metadata({"tenant_id": tenant_id}, record)

    def _find_record_by_source(
        self,
        source: str,
        registry: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not source:
            return None

        registry = registry or self._load_registry()
        source_key = self._normalize_source_path(source)
        filename_key = Path(str(source)).name

        for record in registry.get("documents", {}).values():
            storage_path = self._normalize_source_path(record.get("storage_path"))
            if source_key and storage_path == source_key:
                return record

            record_filename = Path(record.get("storage_name") or record.get("filename") or "").name
            if filename_key and record_filename == filename_key:
                return record

        return None

    def list_frontend_documents(self, role: str) -> List[Dict[str, Any]]:
        return [
            document
            for document in self.list_documents(status="active")
            if self.can_role_access(document, role)
        ]

    def get_frontend_document(self, document_id: str, role: str) -> Dict[str, Any]:
        record = self.get_document(document_id, include_deleted=False)
        if not self.can_role_access(record, role):
            raise FileNotFoundError(document_id)
        return record

    def enqueue_document_index(
        self,
        *,
        document_id: str,
        actor_id: str,
        version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {"document_id": document_id, "version_id": version_id}
        idempotency_version = version_id or "current"
        return task_queue_service.enqueue(
            task_type="knowledge_index_document",
            payload=payload,
            actor_id=actor_id,
            idempotency_key=f"knowledge_index_document:{document_id}:{idempotency_version}",
        )

    def enqueue_reload(self, *, actor_id: str) -> Dict[str, Any]:
        return task_queue_service.enqueue(
            task_type="knowledge_reload",
            payload={},
            actor_id=actor_id,
            idempotency_key="knowledge_reload:latest",
        )

    def index_document(self, document_id: str) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(document_id, registry)
        if record.get("deleted"):
            raise ValueError("cannot index deleted document")

        file_path = self._record_storage_path(record)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(document_id)

        try:
            self._delete_chunks(str(file_path.resolve()))
        except Exception:
            pass
        chunk_count = self._index_file(file_path)
        record["chunk_count"] = chunk_count
        record["updated_at"] = self._now_iso()
        registry["documents"][document_id] = record
        self._save_registry(registry)
        return {"document_id": document_id, "chunk_count": chunk_count}

    def reload_all_documents(self) -> Dict[str, Any]:
        rag_tool = get_rag_tool()
        runtime_params = rag_params_manager.get_params()
        chunk_size = runtime_params.get("chunk_size", 400)
        chunk_overlap = runtime_params.get("chunk_overlap", 50)

        if not rag_tool.clear_and_rebuild_collection():
            raise RuntimeError("failed to rebuild vector collection")

        registry = self._load_registry()
        total_chunks = 0
        indexed_documents = 0
        for document_id, record in registry.get("documents", {}).items():
            if record.get("deleted"):
                continue
            file_path = self._record_storage_path(record)
            if not file_path.exists() or file_path.suffix.lower() not in ALLOWED_DOC_EXTENSIONS:
                continue
            documents = rag_tool.load_document(
                str(file_path),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            doc_ids = rag_tool.add_documents_to_vector_db(documents)
            chunk_count = len(doc_ids)
            record["chunk_count"] = chunk_count
            record["updated_at"] = self._now_iso()
            registry["documents"][document_id] = record
            total_chunks += chunk_count
            indexed_documents += 1

        self._save_registry(registry)
        verified_chunks = rag_tool.collection.count() if rag_tool.collection else total_chunks
        return {
            "success": True,
            "message": "knowledge base reloaded",
            "document_count": indexed_documents,
            "total_chunks": total_chunks,
            "verified_chunks": verified_chunks,
            "access_metadata_rebuilt": True,
            "access_policy_version": self.get_access_policy_version(),
            "params_used": {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
        }

    def list_document_versions(self, document_id: str) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(document_id, registry)
        manifest = self._load_manifest(document_id)
        versions = list(reversed(manifest.get("versions", [])))
        current_version_id = record.get("current_version_id") or manifest.get("current_version_id")
        return {
            "document_id": document_id,
            "current_version_id": current_version_id,
            "versions": [
                {
                    **version,
                    "is_current": version["version_id"] == current_version_id,
                }
                for version in versions
            ],
        }

    def get_document_version(self, document_id: str, version_id: str) -> Dict[str, Any]:
        versions_payload = self.list_document_versions(document_id)
        for version in versions_payload["versions"]:
            if version["version_id"] == version_id:
                return version
        raise FileNotFoundError(version_id)

    def create_document(
        self,
        *,
        filename: str,
        content: bytes,
        actor_id: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        published: bool = False,
        visible_to_frontend: bool = False,
        allowed_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        safe = self._safe_filename(filename)
        registry = self._load_registry()
        if self._find_document_id_by_filename(safe, registry) is not None or (self.docs_dir / safe).exists():
            raise FileExistsError(safe)

        file_path = self.docs_dir / safe
        file_path.write_bytes(content)
        try:
            chunk_count = self._index_file(file_path)
        except Exception:
            if file_path.exists():
                file_path.unlink()
            raise

        now = self._now_iso()
        document_id = self._new_document_id()
        record = self._build_record(document_id=document_id, file_path=file_path, filename=safe)
        record.update(
            {
                "description": description.strip(),
                "tags": self._normalize_tags(tags),
                "published": bool(published),
                "visible_to_frontend": bool(visible_to_frontend),
                "allowed_roles": self._normalize_roles(allowed_roles),
                "deleted": False,
                "created_at": now,
                "created_by": actor_id,
                "updated_at": now,
                "updated_by": actor_id,
                "deleted_at": None,
                "deleted_by": None,
                "chunk_count": chunk_count,
            }
        )
        registry["documents"][document_id] = record
        snapshot = self._append_version_snapshot(record=record, actor_id=actor_id, action="create")
        record["current_version_id"] = snapshot["version_id"]
        registry["documents"][document_id] = record
        self._save_registry(registry)
        self.audit_log_service.write(
            actor_id=actor_id,
            module="knowledge",
            action="create_document",
            target_type="document",
            target_id=document_id,
            result="success",
            extra={
                "filename": safe,
                "chunk_count": chunk_count,
                "published": record["published"],
                "visible_to_frontend": record["visible_to_frontend"],
            },
        )
        return self._serialize_record(record)

    def replace_document(
        self,
        document_id: str,
        *,
        filename: str,
        content: bytes,
        actor_id: str,
    ) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(document_id, registry)
        if record.get("deleted"):
            raise ValueError("cannot replace deleted document")
        self._load_manifest(document_id)

        safe = self._safe_filename(filename)
        conflict_id = self._find_document_id_by_filename(safe, registry)
        if conflict_id is not None and conflict_id != document_id:
            raise FileExistsError(safe)

        old_path = self._record_storage_path(record)
        new_path = self.docs_dir / safe
        if old_path != new_path and new_path.exists():
            raise FileExistsError(safe)

        old_source = str(old_path.resolve()) if old_path.exists() else str(old_path)
        old_bytes = old_path.read_bytes() if old_path.exists() else None
        old_checksum = record.get("checksum")
        old_chunk_count = int(record.get("chunk_count", 0) or 0)

        try:
            self._delete_chunks(old_source)
            if old_path != new_path and old_path.exists():
                old_path.unlink()
            new_path.write_bytes(content)
            chunk_count = self._index_file(new_path)
        except Exception:
            if new_path.exists():
                new_path.unlink()
            if old_bytes is not None:
                old_path.write_bytes(old_bytes)
                try:
                    self._index_file(old_path)
                except Exception:
                    pass
            raise

        now = self._now_iso()
        updated = self._build_record(document_id=document_id, file_path=new_path, filename=safe, legacy=record)
        updated.update(
            {
                "current_version_id": record.get("current_version_id"),
                "description": record.get("description", ""),
                "tags": self._normalize_tags(record.get("tags", [])),
                "published": bool(record.get("published", True)),
                "visible_to_frontend": bool(record.get("visible_to_frontend", True)),
                "allowed_roles": self._normalize_roles(record.get("allowed_roles")),
                "deleted": False,
                "updated_at": now,
                "updated_by": actor_id,
                "chunk_count": chunk_count,
                "deleted_at": None,
                "deleted_by": None,
            }
        )
        snapshot = self._append_version_snapshot(record=updated, actor_id=actor_id, action="replace")
        updated["current_version_id"] = snapshot["version_id"]
        registry["documents"][document_id] = updated
        self._save_registry(registry)
        self.audit_log_service.write(
            actor_id=actor_id,
            module="knowledge",
            action="replace_document",
            target_type="document",
            target_id=document_id,
            result="success",
            extra={
                "filename": safe,
                "old_checksum": old_checksum,
                "new_checksum": updated["checksum"],
                "old_chunk_count": old_chunk_count,
                "new_chunk_count": chunk_count,
            },
        )
        return self._serialize_record(updated)

    def update_document_metadata(
        self,
        document_id: str,
        *,
        actor_id: Optional[str],
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        visible_to_frontend: Optional[bool] = None,
        published: Optional[bool] = None,
        allowed_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(document_id, registry, create_from_filename=True)

        if description is not None:
            record["description"] = description.strip()
        if tags is not None:
            record["tags"] = self._normalize_tags(tags)
        if visible_to_frontend is not None:
            record["visible_to_frontend"] = bool(visible_to_frontend)
        if published is not None:
            record["published"] = bool(published)
        if allowed_roles is not None:
            record["allowed_roles"] = self._normalize_roles(allowed_roles)

        record["updated_at"] = self._now_iso()
        if actor_id:
            record["updated_by"] = actor_id
        registry["documents"][document_id] = record
        self._save_registry(registry)

        if actor_id:
            self.audit_log_service.write(
                actor_id=actor_id,
                module="knowledge",
                action="update_document",
                target_type="document",
                target_id=document_id,
                result="success",
                extra={
                    "filename": record["filename"],
                    "published": record["published"],
                    "visible_to_frontend": record["visible_to_frontend"],
                    "allowed_roles": record["allowed_roles"],
                    "tags": record.get("tags", []),
                },
            )

        return self._serialize_record(record)

    def update_document_access(
        self,
        filename: str,
        visible_to_frontend: Optional[bool] = None,
        published: Optional[bool] = None,
        allowed_roles: Optional[List[str]] = None,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(filename, registry, create_from_filename=True)

        if visible_to_frontend is not None:
            record["visible_to_frontend"] = bool(visible_to_frontend)
        if published is not None:
            record["published"] = bool(published)
        if allowed_roles is not None:
            record["allowed_roles"] = self._normalize_roles(allowed_roles)

        record["updated_at"] = self._now_iso()
        if actor_id:
            record["updated_by"] = actor_id
        registry["documents"][document_id] = record
        self._save_registry(registry)

        if actor_id:
            self.audit_log_service.write(
                actor_id=actor_id,
                module="knowledge",
                action="update_access",
                target_type="document",
                target_id=document_id,
                result="success",
                extra={
                    "filename": record["filename"],
                    "visible_to_frontend": record["visible_to_frontend"],
                    "published": record["published"],
                    "allowed_roles": record["allowed_roles"],
                },
            )

        return self._serialize_record(record)

    def delete_document(self, document_id: str, *, actor_id: str) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(document_id, registry)
        if record.get("deleted"):
            raise ValueError("document already deleted")

        source_path = self._record_storage_path(record)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(document_id)

        trash_path = self.trash_dir / Path(record.get("storage_name") or record.get("filename") or "").name
        if trash_path.exists():
            raise FileExistsError(trash_path.name)

        source = str(source_path.resolve())
        source_path.replace(trash_path)
        try:
            deleted_chunks = self._delete_chunks(source)
        except Exception:
            trash_path.replace(source_path)
            raise

        now = self._now_iso()
        record.update(
            {
                "deleted": True,
                "deleted_at": now,
                "deleted_by": actor_id,
                "updated_at": now,
                "updated_by": actor_id,
                "chunk_count": 0,
                "storage_path": str(trash_path.resolve()),
            }
        )
        registry["documents"][document_id] = record
        self._save_registry(registry)
        self.audit_log_service.write(
            actor_id=actor_id,
            module="knowledge",
            action="delete_document",
            target_type="document",
            target_id=document_id,
            result="success",
            extra={
                "filename": record["filename"],
                "deleted_chunks": deleted_chunks,
            },
        )
        return self._serialize_record(record)

    def restore_document(self, document_id: str, *, actor_id: str) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, record = self._resolve_record(document_id, registry)
        if not record.get("deleted"):
            raise ValueError("document is not deleted")

        source_path = self._record_storage_path(record)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(document_id)

        target_path = self.docs_dir / Path(record.get("storage_name") or record.get("filename") or "").name
        if target_path.exists():
            raise FileExistsError(target_path.name)

        source_path.replace(target_path)
        try:
            chunk_count = self._index_file(target_path)
        except Exception:
            target_path.replace(source_path)
            raise

        now = self._now_iso()
        restored = self._build_record(
            document_id=document_id,
            file_path=target_path,
            filename=record.get("filename") or target_path.name,
            legacy=record,
        )
        restored.update(
            {
                "deleted": False,
                "deleted_at": None,
                "deleted_by": None,
                "published": False,
                "visible_to_frontend": False,
                "updated_at": now,
                "updated_by": actor_id,
                "chunk_count": chunk_count,
            }
        )
        registry["documents"][document_id] = restored
        self._save_registry(registry)
        self.audit_log_service.write(
            actor_id=actor_id,
            module="knowledge",
            action="restore_document",
            target_type="document",
            target_id=document_id,
            result="success",
            extra={
                "filename": restored["filename"],
                "chunk_count": chunk_count,
                "published": restored["published"],
                "visible_to_frontend": restored["visible_to_frontend"],
            },
        )
        return self._serialize_record(restored)

    def rollback_document(
        self,
        document_id: str,
        *,
        target_version_id: str,
        actor_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        registry = self._load_registry()
        document_id, current = self._resolve_record(document_id, registry)
        if current.get("deleted"):
            raise KnowledgeConflictError("restore the document before rollback")

        target = self.get_document_version(document_id, target_version_id)
        snapshot_path = Path(target["snapshot_storage_path"])
        if not snapshot_path.exists() or not snapshot_path.is_file():
            raise KnowledgeConflictError("snapshot file is unavailable for rollback")

        target_filename = self._safe_filename(target["filename"])
        conflict_id = self._find_document_id_by_filename(target_filename, registry)
        if conflict_id is not None and conflict_id != document_id:
            raise FileExistsError(target_filename)

        current_path = self._record_storage_path(current)
        target_path = self.docs_dir / target_filename
        if target_path != current_path and target_path.exists():
            raise FileExistsError(target_filename)

        manifest_path = self._manifest_path(document_id)
        registry_before = self.metadata_path.read_text(encoding="utf-8") if self.metadata_path.exists() else None
        manifest_before = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        current_source = str(current_path.resolve())
        current_bytes = current_path.read_bytes() if current_path.exists() else None
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot = None

        try:
            self._delete_chunks(current_source)
            if target_path != current_path and current_path.exists():
                current_path.unlink()
            target_path.write_bytes(snapshot_bytes)
            chunk_count = self._index_file(target_path)
            now = self._now_iso()
            rolled = self._build_record(
                document_id=document_id,
                file_path=target_path,
                filename=target_filename,
                legacy=current,
            )
            rolled.update(
                {
                    "current_version_id": current.get("current_version_id"),
                    "description": target.get("description", ""),
                    "tags": self._normalize_tags(target.get("tags", [])),
                    "published": bool(current.get("published", True)),
                    "visible_to_frontend": bool(current.get("visible_to_frontend", True)),
                    "allowed_roles": self._normalize_roles(current.get("allowed_roles")),
                    "deleted": bool(current.get("deleted", False)),
                    "created_at": current.get("created_at"),
                    "created_by": current.get("created_by"),
                    "updated_at": now,
                    "updated_by": actor_id,
                    "deleted_at": current.get("deleted_at"),
                    "deleted_by": current.get("deleted_by"),
                    "chunk_count": chunk_count,
                }
            )
            snapshot = self._append_version_snapshot(
                record=rolled,
                actor_id=actor_id,
                action="rollback",
                reason=reason,
                source_version_id=target_version_id,
            )
            rolled["current_version_id"] = snapshot["version_id"]
            registry["documents"][document_id] = rolled
            self._save_registry(registry)
            self.audit_log_service.write(
                actor_id=actor_id,
                module="knowledge",
                action="knowledge.version.rollback",
                target_type="document",
                target_id=document_id,
                result="success",
                extra={
                    "target_version_id": target_version_id,
                    "new_version_id": snapshot["version_id"],
                    "reason": reason,
                    "old_checksum": current.get("checksum"),
                    "new_checksum": rolled.get("checksum"),
                    "old_chunk_count": current.get("chunk_count", 0),
                    "new_chunk_count": rolled.get("chunk_count", 0),
                },
            )
            return self._serialize_record(rolled)
        except Exception:
            if snapshot is not None:
                snapshot_dir = Path(snapshot["snapshot_storage_path"]).parent
                if snapshot_dir.exists():
                    for child in snapshot_dir.iterdir():
                        child.unlink()
                    snapshot_dir.rmdir()
            if manifest_before is None:
                if manifest_path.exists():
                    manifest_path.unlink()
            else:
                manifest_path.write_text(manifest_before, encoding="utf-8")
            if registry_before is None:
                if self.metadata_path.exists():
                    self.metadata_path.unlink()
            else:
                self.metadata_path.write_text(registry_before, encoding="utf-8")
            self._delete_chunks(str(target_path.resolve()))
            if target_path.exists():
                target_path.unlink()
            if current_bytes is not None:
                current_path.write_bytes(current_bytes)
                try:
                    self._index_file(current_path)
                except Exception:
                    pass
            raise


knowledge_admin_service = KnowledgeAdminService()
