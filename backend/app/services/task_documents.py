from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings
from app.retrieval import RetrievalDepth, RetrievalRequest, get_retriever
from app.retrieval.sources.local import LocalFileLoader

_SUPPORTED_UPLOAD_EXTENSIONS = {".md", ".txt"}


class DocumentUploadError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def decode_upload_document(content: bytes) -> str:
    if not content.strip():
        raise DocumentUploadError("VALIDATION_ERROR", "Uploaded document is empty.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    if not text.strip():
        raise DocumentUploadError("VALIDATION_ERROR", "Uploaded document is empty.")
    return text


def _ensure_supported_filename(filename: str) -> str:
    clean_name = _safe_filename(filename)
    suffix = Path(clean_name).suffix.lower()
    if suffix not in _SUPPORTED_UPLOAD_EXTENSIONS:
        raise DocumentUploadError(
            "VALIDATION_ERROR",
            "Only .md and .txt uploads are supported.",
            {"supported_extensions": sorted(_SUPPORTED_UPLOAD_EXTENSIONS)},
        )
    return clean_name


def _write_task_document_file(task_id: str, filename: str, text: str) -> dict[str, Any]:
    clean_name = _ensure_supported_filename(filename)
    document_id = f"doc_{uuid4().hex[:12]}"
    task_dir = task_documents_dir(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{document_id}_{clean_name}"
    file_path = task_dir / stored_name
    file_path.write_text(text, encoding="utf-8")

    chunks = LocalFileLoader(task_dir).load()
    chunk_count = sum(1 for chunk in chunks if chunk.source_id == stored_name)
    return {
        "document_id": document_id,
        "filename": clean_name,
        "stored_filename": stored_name,
        "status": "ready",
        "chunk_count": chunk_count,
    }


def save_task_document(task_id: str, filename: str, content: bytes) -> dict[str, Any]:
    max_bytes = max(1, settings.task_document_upload_max_bytes)
    if len(content) > max_bytes:
        raise DocumentUploadError(
            "VALIDATION_ERROR",
            "Uploaded document is too large.",
            {"max_bytes": max_bytes},
        )
    text = decode_upload_document(content)
    return _write_task_document_file(task_id, filename, text)


def save_task_document_text(
    task_id: str,
    text: str,
    *,
    filename: str = "document.md",
) -> dict[str, Any]:
    body = (text or "").strip()
    if not body:
        raise DocumentUploadError("VALIDATION_ERROR", "Uploaded document is empty.")
    max_bytes = max(1, settings.task_document_upload_max_bytes)
    encoded = body.encode("utf-8")
    if len(encoded) > max_bytes:
        raise DocumentUploadError(
            "VALIDATION_ERROR",
            "Uploaded document is too large.",
            {"max_bytes": max_bytes},
        )
    return _write_task_document_file(task_id, filename, body)


def filename_for_document_title(document_title: str | None) -> str:
    stem = _safe_filename(document_title or "document").rsplit(".", 1)[0] or "document"
    return f"{stem}.md"


def public_attachment(attachment: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(attachment.get("document_id") or ""),
        "filename": str(attachment.get("filename") or ""),
        "status": str(attachment.get("status") or "pending"),
        "chunk_count": attachment.get("chunk_count"),
    }


def task_documents_dir(task_id: str) -> Path:
    return Path(settings.task_documents_dir) / _safe_path_part(task_id)


def task_chroma_dir(task_id: str) -> Path:
    return Path(settings.task_documents_chroma_dir) / _safe_path_part(task_id)


async def retrieve_task_document_hits(
    *,
    task_id: str,
    query: str,
    depth: RetrievalDepth,
    max_results: int = 3,
) -> list[dict[str, Any]]:
    docs_dir = task_documents_dir(task_id)
    if not docs_dir.is_dir():
        return []

    retriever = get_retriever(
        documents_dir=str(docs_dir),
        chroma_persist_dir=str(task_chroma_dir(task_id)),
        tavily_api_key="",
    )
    result = await retriever.retrieve(RetrievalRequest(query=query, depth=depth, max_results=max_results))
    hits: list[dict[str, Any]] = []
    for hit in result.hits[:max_results]:
        payload = hit.model_dump()
        payload["source_id"] = f"user:{payload.get('source_id') or 'attachment'}"
        hits.append(payload)
    return hits


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload.txt").name
    name = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name).strip("._")
    return name or "upload.txt"


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_\-]+", "_", value).strip("_") or "unknown"
