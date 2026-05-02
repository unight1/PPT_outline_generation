from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from openai import OpenAI

from app.config import settings


def should_force_fail(topic: str) -> bool:
    """Test hook: force failed status by topic marker."""
    return "[FAIL]" in topic


def build_stub_outline(retrieval_depth: str) -> dict[str, Any]:
    """Temporary outline generator. Later replaced by real LLM pipeline."""
    generated_at = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    return {
        "title": "AI 时代的高效演示设计",
        "slides": [
            {
                "slide_id": "s1",
                "title": "背景与目标",
                "bullets": [
                    {"bullet_id": "s1-b1", "text": "为什么需要自动化生成 PPT", "evidence_ids": ["ev_1"]},
                    {"bullet_id": "s1-b2", "text": "项目目标与受众收益", "evidence_ids": []},
                ],
                "speaker_notes": "先讲问题，再讲目标。",
            }
        ],
        "evidence_catalog": [
            {
                "evidence_id": "ev_1",
                "snippet": "知识工作者每周平均花费数小时整理演示材料。",
                "source_id": "demo_source",
                "locator": "段落 1",
                "score": 0.8,
                "confidence": 0.7,
            }
        ],
        "meta": {
            "retrieval_depth": retrieval_depth,
            "generated_at": generated_at,
            "mode": "fake",
            "schema_version": settings.outline_schema_version,
        },
    }


def _outline_prompt(topic: str, retrieval_depth: str) -> str:
    return f"""
你是一个PPT大纲助手。请只输出一个JSON对象，且必须符合以下结构：
{{
  "title": "string",
  "slides": [
    {{
      "slide_id": "s1",
      "title": "string",
      "bullets": [
        {{
          "bullet_id": "s1-b1",
          "text": "string",
          "evidence_ids": ["ev_1"]
        }}
      ],
      "speaker_notes": "string"
    }}
  ],
  "evidence_catalog": [
    {{
      "evidence_id": "ev_1",
      "snippet": "string",
      "source_id": "string",
      "locator": "string",
      "score": 0.0,
      "confidence": 0.0
    }}
  ],
  "meta": {{
    "retrieval_depth": "{retrieval_depth}",
    "generated_at": "ISO8601"
  }}
}}

硬性要求：
1) slides 至少 5 页；
2) 内容应包含引言/主体/结论逻辑；
3) 每页至少 2 个 bullet；
4) 若没有可靠证据，可让 evidence_catalog 为空数组，并将 bullets 中 evidence_ids 设为空数组；
5) 不要输出 Markdown，不要输出解释文字，只输出 JSON。

用户主题：{topic}
""".strip()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_outline(raw: dict[str, Any], retrieval_depth: str) -> dict[str, Any]:
    slides_in = raw.get("slides", []) if isinstance(raw.get("slides", []), list) else []
    slides: list[dict[str, Any]] = []
    for idx, slide in enumerate(slides_in[:20], start=1):
        if not isinstance(slide, dict):
            continue
        bullets_in = slide.get("bullets", []) if isinstance(slide.get("bullets", []), list) else []
        bullets: list[dict[str, Any]] = []
        for jdx, bullet in enumerate(bullets_in[:8], start=1):
            if not isinstance(bullet, dict):
                continue
            evidence_ids_raw = bullet.get("evidence_ids", [])
            evidence_ids = evidence_ids_raw if isinstance(evidence_ids_raw, list) else []
            bullets.append(
                {
                    "bullet_id": str(bullet.get("bullet_id") or f"s{idx}-b{jdx}"),
                    "text": str(bullet.get("text") or "待补充要点"),
                    "evidence_ids": [str(eid) for eid in evidence_ids],
                }
            )
        if len(bullets) < 2:
            bullets.append({"bullet_id": f"s{idx}-b{len(bullets)+1}", "text": "待补充要点", "evidence_ids": []})
        slides.append(
            {
                "slide_id": str(slide.get("slide_id") or f"s{idx}"),
                "title": str(slide.get("title") or f"第{idx}页"),
                "bullets": bullets,
                "speaker_notes": str(slide.get("speaker_notes") or ""),
            }
        )

    while len(slides) < 5:
        idx = len(slides) + 1
        slides.append(
            {
                "slide_id": f"s{idx}",
                "title": f"第{idx}页",
                "bullets": [
                    {"bullet_id": f"s{idx}-b1", "text": "待补充要点", "evidence_ids": []},
                    {"bullet_id": f"s{idx}-b2", "text": "待补充要点", "evidence_ids": []},
                ],
                "speaker_notes": "",
            }
        )

    evidence_in = raw.get("evidence_catalog", []) if isinstance(raw.get("evidence_catalog", []), list) else []
    evidence_catalog: list[dict[str, Any]] = []
    for idx, ev in enumerate(evidence_in[:50], start=1):
        if not isinstance(ev, dict):
            continue
        evidence_catalog.append(
            {
                "evidence_id": str(ev.get("evidence_id") or f"ev_{idx}"),
                "snippet": str(ev.get("snippet") or ""),
                "source_id": str(ev.get("source_id") or "unknown"),
                "locator": str(ev.get("locator") or ""),
                "score": _safe_float(ev.get("score")),
                "confidence": _safe_float(ev.get("confidence")),
            }
        )

    now = datetime.now(timezone.utc).isoformat()
    return {
        "title": str(raw.get("title") or "自动生成演示文稿"),
        "slides": slides,
        "evidence_catalog": evidence_catalog,
        "meta": {
            "retrieval_depth": retrieval_depth,
            "generated_at": now,
            "mode": "real",
            "model": settings.llm_model,
            "schema_version": settings.outline_schema_version,
        },
    }


def _extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise RuntimeError("LLM returned empty content.")
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


def build_real_outline(topic: str, retrieval_depth: str) -> dict[str, Any]:
    """Generate outline via real LLM call and normalize output shape."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required when USE_REAL_LLM=true.")

    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "你是严谨的JSON生成器。"},
            {"role": "user", "content": _outline_prompt(topic=topic, retrieval_depth=retrieval_depth)},
        ],
        "temperature": 0.3,
        "timeout": settings.llm_timeout_seconds,
    }
    try:
        # Some OpenAI-compatible gateways support strict JSON mode.
        response = client.chat.completions.create(response_format={"type": "json_object"}, **payload)
    except Exception:
        # DeepSeek-compatible gateways may reject response_format; retry without it.
        response = client.chat.completions.create(**payload)

    content = response.choices[0].message.content or "{}"
    raw = _extract_json_object(content)
    return _normalize_outline(raw=raw, retrieval_depth=retrieval_depth)


def generate_outline(topic: str, retrieval_depth: str) -> dict[str, Any]:
    if settings.use_real_llm:
        return build_real_outline(topic=topic, retrieval_depth=retrieval_depth)
    return build_stub_outline(retrieval_depth=retrieval_depth)
