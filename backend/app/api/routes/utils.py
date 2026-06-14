from __future__ import annotations

import io
import json
import logging
import re

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.config import settings

router = APIRouter(prefix="/utils", tags=["utils"])
logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 5_000_000


class AnalyzeRequest(BaseModel):
    document_text: str = Field(min_length=1, max_length=100_000)


@router.post("/analyze-document")
def analyze_document(payload: AnalyzeRequest) -> dict[str, str]:
    if not settings.use_real_llm or not settings.openai_api_key:
        return {}

    from openai import OpenAI

    client_kwargs: dict = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    text = payload.document_text[:4000]
    prompt = f"""你是专业的文档分析助手。请根据以下文档内容，为创建PPT演示任务提供建议。

文档内容：
{text}

请只输出一个JSON对象，结构如下：
{{
  "topic": "建议的PPT大标题，不超过40字，概括文档核心主题",
  "audience": "建议的听众/场景描述，如：课程答辩、产品汇报、学术报告等，不超过20字",
  "notes": "补充建议，如：重点应涵盖哪些方面、应避免哪些话题、页数建议等，不超过100字"
}}

不要输出Markdown或解释文字，只输出JSON。"""

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "你是严谨的JSON生成器。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            timeout=settings.llm_timeout_seconds,
        )
        content = (response.choices[0].message.content or "{}").strip()

        # Extract JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", content)
            result = json.loads(match.group(0)) if match else {}

        return {
            "topic": str(result.get("topic") or ""),
            "audience": str(result.get("audience") or ""),
            "notes": str(result.get("notes") or ""),
        }
    except Exception as exc:
        logger.warning("Document analysis failed: %s", exc)
        return {}


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
