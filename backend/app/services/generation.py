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


def build_stub_outline(retrieval_depth: str, target_pages: int = 5) -> dict[str, Any]:
    """Temporary outline generator. Later replaced by real LLM pipeline."""
    generated_at = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    slides = [
        {
            "slide_id": "s1",
            "title": "背景与目标",
            "bullets": [
                {"bullet_id": "s1-b1", "text": "为什么需要自动化生成 PPT", "evidence_ids": ["ev_1"]},
                {"bullet_id": "s1-b2", "text": "项目目标与受众收益", "evidence_ids": []},
            ],
            "speaker_notes": "先讲问题，再讲目标。",
        }
    ]
    while len(slides) < max(5, target_pages):
        idx = len(slides) + 1
        slides.append(
            {
                "slide_id": f"s{idx}",
                "title": f"第{idx}页核心内容",
                "bullets": [
                    {"bullet_id": f"s{idx}-b1", "text": "关键结论与价值说明", "evidence_ids": []},
                    {"bullet_id": f"s{idx}-b2", "text": "支撑逻辑与下一步动作", "evidence_ids": []},
                ],
                "speaker_notes": "说明该页核心结论，并衔接下一页。",
            }
        )

    return {
        "title": "AI 时代的高效演示设计",
        "slides": slides,
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


def _outline_prompt(topic: str, retrieval_depth: str, target_pages: int) -> str:
    return f"""
你是一个资深咨询顾问风格的PPT内容策划助手。请生成“可直接讲述”的高质量初稿，而不是空泛提纲。
请只输出一个JSON对象，且必须符合以下结构：
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
1) slides 必须为 {max(5, target_pages)} 页，不多不少；
2) 内容应包含引言/主体/结论逻辑；
3) 每页建议 3-5 个 bullet，且 bullet 文本必须具体，避免“待补充/进一步分析”等空话；
4) bullet 要覆盖：关键结论、原因/机制、可执行动作、风险或边界（按页选择）；
5) 每页 speaker_notes 必须是 2-4 句可讲述话术，说明“这页要讲什么、怎么过渡到下一页”；
6) 至少 2 页包含“数据/案例/对比”类型要点（可用行业通用范围表达，避免编造精确不可验证数字）；
7) evidence_catalog 优先给出可追溯证据；若没有可靠证据，可为空数组，但 bullets 中 evidence_ids 需保持为空数组；
8) 页面标题要有信息量，不要仅写“背景/方案/总结”这类过泛词，建议写成“结论+对象”形式；
9) 不要输出 Markdown，不要输出解释文字，只输出 JSON。
10) 严禁编造事实、来源、统计值、年份、机构结论；若输入中没有可核验依据，必须使用“趋势/常见现象/可能风险”等非定量表达；
11) 若未提供明确证据文本，禁止输出精确数字（如百分比、金额、样本量、排名、年份）；可改为“显著提升/明显下降/行业普遍”等定性表述。

质量偏好（重要）：
- 用语简洁、专业、可讲，避免口号式表述。
- 各页之间要有递进：问题定义 -> 分析框架 -> 方案设计 -> 落地计划 -> 风险与结论。
- 若主题偏技术，优先加入“架构、流程、权衡、指标”；若偏业务，优先加入“目标、路径、收益、风险”。

用户主题：{topic}
""".strip()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_outline(raw: dict[str, Any], retrieval_depth: str, target_pages: int) -> dict[str, Any]:
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

    desired_pages = max(5, int(target_pages))
    while len(slides) < desired_pages:
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


def build_real_outline(topic: str, retrieval_depth: str, target_pages: int = 5) -> dict[str, Any]:
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
            {
                "role": "user",
                "content": _outline_prompt(
                    topic=topic,
                    retrieval_depth=retrieval_depth,
                    target_pages=target_pages,
                ),
            },
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
    return _normalize_outline(raw=raw, retrieval_depth=retrieval_depth, target_pages=target_pages)


def generate_outline(topic: str, retrieval_depth: str, target_pages: int = 5) -> dict[str, Any]:
    if settings.use_real_llm:
        return build_real_outline(topic=topic, retrieval_depth=retrieval_depth, target_pages=target_pages)
    return build_stub_outline(retrieval_depth=retrieval_depth, target_pages=target_pages)
