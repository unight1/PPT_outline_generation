from __future__ import annotations

import logging
import re
from typing import Any

from openai import OpenAI

from app.config import settings
from app.services.document_processing import build_document_profile

logger = logging.getLogger(__name__)

_SEGMENT_SIZE = 2000
_LONG_DOC_THRESHOLD = 4000
_SUMMARY_MAX_CHARS = 2500
_KEY_POINTS_MAX = 12
_KEY_POINTS_MIN = 3


def _segment_long_text(text: str, size: int = _SEGMENT_SIZE) -> list[str]:
    parts: list[str] = []
    for start in range(0, len(text), size):
        end = min(start + size, len(text))
        part = text[start:end].strip()
        if part:
            parts.append(part)
    if not parts:
        parts = [text[:size]]
    return parts


def _llm_summarize(client: OpenAI, text: str) -> str:
    truncated = text[:_SUMMARY_MAX_CHARS]
    prompt = (
        "你是专业的文档分析师。请为以下文档撰写一段简洁的摘要（约100-200字），"
        "提炼核心内容和关键观点。\n\n"
        f"文档内容：\n{truncated}\n\n"
        "请只输出摘要文本，不要加前缀或解释。"
    )
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": "你是严谨的文档分析师，只输出摘要。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        timeout=settings.llm_timeout_seconds,
    )
    return (response.choices[0].message.content or "").strip()


def _llm_summarize_long_document(client: OpenAI, text: str) -> str:
    segments = _segment_long_text(text, size=2000)
    if len(segments) <= 1:
        return _llm_summarize(client, text)

    segment_summaries: list[str] = []
    for idx, segment in enumerate(segments[:8], start=1):
        try:
            seg_summary = _llm_summarize(client, segment)
            if seg_summary:
                segment_summaries.append(f"[第{idx}段] {seg_summary}")
        except Exception:
            logger.warning("Segment %d summary failed, skipped", idx)

    if not segment_summaries:
        return text[:_SUMMARY_MAX_CHARS].strip()

    if len(segment_summaries) == 1:
        return segment_summaries[0]

    combined = "\n".join(segment_summaries)
    merge_prompt = (
        "你是专业的文档分析师。以下是一篇长文档各分段的摘要，"
        "请将它们合并为一段连贯的全文摘要（约150-300字）。\n\n"
        f"{combined}\n\n"
        "请只输出合并后的摘要文本，不要加前缀或解释。"
    )
    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "你是文档分析师，只输出合并摘要。"},
                {"role": "user", "content": merge_prompt},
            ],
            temperature=0.3,
            timeout=settings.llm_timeout_seconds,
        )
        merged = (response.choices[0].message.content or "").strip()
        if merged:
            return merged
    except Exception:
        logger.warning("Merging segment summaries failed, joining raw")

    return "\n".join(segment_summaries)


def _llm_extract_key_points(client: OpenAI, text: str) -> list[str]:
    truncated = text[:_SUMMARY_MAX_CHARS]
    prompt = (
        "你是专业的文档分析师。请从以下文档中提取关键要点，每条约30-80字。\n\n"
        f"文档内容：\n{truncated}\n\n"
        "请用以下格式输出，每行一条：\n"
        "1. 要点一\n2. 要点二"
    )
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": "你是文档分析师，只输出要点列表。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        timeout=settings.llm_timeout_seconds,
    )
    content = (response.choices[0].message.content or "").strip()
    return _parse_key_points(content)


def _parse_key_points(content: str) -> list[str]:
    lines = content.split("\n")
    points: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^[\d\-•·\*]+\s*[.、]?\s*(.+)", line)
        if match:
            points.append(match.group(1).strip())
        elif len(line) >= 8 and not line.startswith(("#", "//", "<!--")):
            points.append(line)
    return points[:_KEY_POINTS_MAX]


def _llm_suggest_focus(client: OpenAI, text: str, topic: str) -> str | None:
    truncated = text[:2000]
    prompt = (
        "你是专业的PPT策划顾问。请基于以下文档内容和主题，建议PPT的叙事侧重方向（约50-100字）。\n\n"
        f"主题：{topic}\n"
        f"文档内容：\n{truncated}\n\n"
        "请只输出建议文本，不要加前缀或解释。"
    )
    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "你是PPT策划顾问，只输出建议。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            timeout=settings.llm_timeout_seconds,
        )
        result = (response.choices[0].message.content or "").strip()
        return result if result else None
    except Exception:
        logger.warning("Suggested focus generation failed")
        return None


def enrich_document_profile(
    document_text: str,
    topic: str = "",
    document_title: str = "",
) -> dict[str, Any]:
    text = " ".join((document_text or "").split()).strip()
    if not text:
        return {}

    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    summary: str = ""
    try:
        if len(text) > _LONG_DOC_THRESHOLD:
            summary = _llm_summarize_long_document(client, text)
        else:
            summary = _llm_summarize(client, text)
    except Exception as exc:
        logger.warning("LLM summary failed: %s", exc)

    key_points: list[str] = []
    try:
        key_points = _llm_extract_key_points(client, text)
    except Exception as exc:
        logger.warning("LLM key points extraction failed: %s", exc)

    suggested_focus: str | None = None
    try:
        suggested_focus = _llm_suggest_focus(client, text, topic)
    except Exception as exc:
        logger.warning("LLM suggested focus failed: %s", exc)

    enrichment: dict[str, Any] = {}
    if summary:
        enrichment["summary"] = summary[:2000]
    if len(key_points) >= _KEY_POINTS_MIN:
        enrichment["key_points"] = key_points
    if suggested_focus:
        enrichment["suggested_focus"] = suggested_focus
    return enrichment


def merge_enrichment_into_profile(
    rule_profile: dict[str, Any] | None,
    enrichment: dict[str, Any],
) -> dict[str, Any]:
    profile = dict(rule_profile or {})
    if enrichment.get("summary"):
        profile["summary"] = enrichment["summary"]
    if enrichment.get("key_points"):
        profile["key_points"] = enrichment["key_points"]
    if enrichment.get("suggested_focus"):
        profile["suggested_focus"] = enrichment["suggested_focus"]
    return profile
