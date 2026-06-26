from __future__ import annotations

import pytest

from app.services.task_documents import (
    DocumentUploadError,
    _ensure_supported_filename,
    _safe_filename,
    _safe_path_part,
    decode_upload_document,
    filename_for_document_title,
    public_attachment,
)


def test_decode_utf8():
    text = decode_upload_document("Hello World".encode("utf-8"))
    assert text == "Hello World"


def test_decode_latin1_fallback():
    text = decode_upload_document("café".encode("latin-1"))
    assert "caf" in text


def test_supported_md_txt():
    assert _ensure_supported_filename("doc.txt") == "doc.txt"
    assert _ensure_supported_filename("doc.md") == "doc.md"


def test_supported_raises_on_pdf():
    with pytest.raises(DocumentUploadError):
        _ensure_supported_filename("doc.pdf")


def test_safe_filename():
    assert _safe_filename("hello world.txt") == "hello_world.txt"
    # Path separators are stripped, leaving filename only
    result = _safe_filename("path/traversal.txt")
    assert "/" not in result


def test_safe_path_part():
    assert _safe_path_part("abc-123_def") == "abc-123_def"
    result = _safe_path_part("bad/../path")
    assert "/" not in result


def test_filename_for_document_title():
    assert "My_Report" in filename_for_document_title("My Report")
    assert filename_for_document_title(None) == "document.md"


def test_public_attachment_strips_internal():
    attachment = {
        "document_id": "d1",
        "filename": "test.txt",
        "status": "ready",
        "chunk_count": 5,
    }
    public = public_attachment(attachment)
    assert public["document_id"] == "d1"
