from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_FORBIDDEN_KEYS = {"options", "type", "choices", "input_type"}


def estimate_page_range(duration_minutes: int) -> str:
    low = max(5, duration_minutes // 2)
    high = max(low + 2, duration_minutes)
    return f"{low}-{high} 页"


def _target_page_answer(payload: Any) -> str:
    min_pages = getattr(payload, "target_pages_min", None)
    max_pages = getattr(payload, "target_pages_max", None)
    if isinstance(min_pages, int) and isinstance(max_pages, int):
        return f"{min_pages}-{max_pages} 页"
    pages = getattr(payload, "target_pages", None)
    if isinstance(pages, int) and pages > 0:
        return f"{pages} 页"
    return estimate_page_range(payload.duration_minutes)


def build_fallback_clarification_questions(payload: Any) -> list[dict[str, Any]]:
    """Return contract-safe text questions when LLM is unavailable or disabled."""
    questions: list[dict[str, Any]] = [
        {
            "question_id": "goal",
            "prompt": f"围绕「{payload.topic}」，本次演示希望听众记住的一个核心结论是什么？",
            "answer": None,
        },
        {
            "question_id": "style",
            "prompt": "希望表达风格偏正式汇报、课堂讲解还是路演展示？",
            "answer": None,
        },
        {
            "question_id": "depth",
            "prompt": "内容深度偏概览、实操还是研究分析？",
            "answer": None,
        },
    ]
    if not (payload.audience or "").strip():
        questions.append(
            {
                "question_id": "audience_level",
                "prompt": "听众对该主题的熟悉程度如何（入门/中等/专业）？",
                "answer": None,
            }
        )
    if not (payload.raw_notes or "").strip():
        questions.append(
            {
                "question_id": "constraints",
                "prompt": "是否有必须包含或必须避免的内容约束？",
                "answer": None,
            }
        )
    if payload.source_type == "long_document" and not (payload.document_title or "").strip():
        questions.append(
            {
                "question_id": "doc_focus",
                "prompt": "长文档中优先提炼哪些章节或观点？",
                "answer": None,
            }
        )
    questions.append(
        {
            "question_id": "page_range",
            "prompt": "期望页数范围是多少（例如 8-12 页）？",
            "answer": _target_page_answer(payload),
        }
    )
    return questions


def build_clarification_questions(
    payload: Any,
    *,
    document_profile: dict[str, Any] | None = None,
    fallback_builder: Callable[[Any], list[dict[str, Any]]] = build_fallback_clarification_questions,
) -> list[dict[str, Any]]:
    """Generate 3-5 text-only clarification questions, falling back to deterministic rules."""
    fallback = fallback_builder(payload)
    if not settings.use_real_llm:
        return fallback
    if not settings.openai_api_key:
        logger.warning("USE_REAL_LLM=true but OPENAI_API_KEY is empty; using fallback clarification questions.")
        return fallback

    try:
        raw_questions = _call_llm(payload, document_profile=document_profile)
        questions = _normalize_questions(raw_questions, fallback=fallback)
        return questions[:5] if len(questions) >= 3 else fallback
    except Exception:
        logger.exception("Clarification LLM generation failed; using fallback questions.")
        return fallback


def _call_llm(payload: Any, *, document_profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    summary = ""
    if isinstance(document_profile, dict):
        summary = str(document_profile.get("summary") or "")
        if not summary:
            key_points = document_profile.get("key_points")
            if isinstance(key_points, list):
                summary = "；".join(str(item) for item in key_points[:3])

    prompt = f"""请为 PPT 大纲生成任务提出 3 到 5 个澄清问题。

输入：
- 主题：{payload.topic}
- 材料类型：{payload.source_type}
- 听众：{payload.audience or "未填写"}
- 时长：{payload.duration_minutes} 分钟
- 语言：{payload.language}
- 用户备注：{payload.raw_notes or "未填写"}
- 文档标题：{payload.document_title or "未填写"}
- 文档摘要：{summary or "无"}

要求：
1. 只输出 JSON 对象，形如 {{"questions":[{{"question_id":"goal","prompt":"...","answer":null}}]}}。
2. questions 长度 3 到 5。
3. 每题只能包含 question_id、prompt、answer 三个字段。
4. 不要输出 options、type、choices、input_type 等选择题字段。
5. 已明确填写的信息不要重复追问；可对时长预填 answer。
6. 题干要贴合主题，主要从内容角度提问，避免泛泛而问。
"""
    payload_kwargs = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "你是严谨的 JSON 生成器，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "timeout": settings.llm_timeout_seconds,
    }
    try:
        response = client.chat.completions.create(response_format={"type": "json_object"}, **payload_kwargs)
    except Exception:
        response = client.chat.completions.create(**payload_kwargs)
    content = response.choices[0].message.content or "{}"
    data = _extract_json_object(content)
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError("clarification output missing questions list")
    return [item for item in questions if isinstance(item, dict)]


def _extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
    if fenced:
        parsed = json.loads(fenced.group(1))
        if isinstance(parsed, dict):
            return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("LLM output is not a JSON object.")


def _normalize_questions(
    raw_questions: list[dict[str, Any]],
    *,
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fallback_by_id = {str(item.get("question_id")): item for item in fallback}
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw_questions, start=1):
        if any(key in item for key in _FORBIDDEN_KEYS):
            item = {key: value for key, value in item.items() if key not in _FORBIDDEN_KEYS}
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        raw_id = str(item.get("question_id") or f"q{idx}").strip()
        question_id = _slugify_question_id(raw_id) or f"q{idx}"
        if question_id in seen:
            question_id = f"{question_id}_{idx}"
        answer = item.get("answer")
        if answer is not None:
            answer = str(answer).strip() or None
        questions.append({"question_id": question_id, "prompt": prompt, "answer": answer})
        seen.add(question_id)
        if len(questions) >= 5:
            break

    if len(questions) < 3:
        for item in fallback:
            question_id = str(item.get("question_id") or "")
            if question_id in seen:
                continue
            questions.append(dict(item))
            seen.add(question_id)
            if len(questions) >= 3:
                break

    if "page_range" in fallback_by_id and not any(q["question_id"] == "page_range" for q in questions):
        if len(questions) < 5:
            questions.append(dict(fallback_by_id["page_range"]))
    return questions[:5]


def _slugify_question_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]+", "_", value).strip("_").lower()
    return cleaned[:40]
