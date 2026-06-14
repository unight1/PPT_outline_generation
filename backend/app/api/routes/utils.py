from __future__ import annotations

import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pypdf import PdfReader

router = APIRouter(prefix="/utils", tags=["utils"])
logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 5_000_000


@router.post("/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "仅支持 .pdf 文件。", "details": {}}},
        )

    content = await file.read()
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VALIDATION_ERROR", "message": f"PDF 文件不能超过 {MAX_PDF_BYTES // 1_000_000}MB。", "details": {}}},
        )

    try:
        reader = PdfReader(io.BytesIO(content))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        full_text = "\n\n".join(pages)
        if not full_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": {"code": "VALIDATION_ERROR", "message": "PDF 文件无法提取文本内容，可能是扫描件或图片型 PDF。", "details": {}}},
            )
        logger.info("PDF parsed filename=%s pages=%d chars=%d", file.filename, len(pages), len(full_text))
        return {"text": full_text, "pages": str(len(pages)), "filename": file.filename or "unknown.pdf"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PDF parsing failed filename=%s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL_ERROR", "message": f"PDF 解析失败：{exc}", "details": {}}},
        ) from exc
