from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.config import settings


def infer_target_pages(clarification: dict[str, Any] | None, raw_notes: str | None = None) -> int:
    """Infer a practical slide count from user clarification answers."""

    hints: list[str] = []
    if isinstance(raw_notes, str) and raw_notes.strip():
        hints.append(raw_notes)
    if isinstance(clarification, dict):
        questions = clarification.get("questions", [])
        if isinstance(questions, list):
            for item in questions:
                if not isinstance(item, dict):
                    continue
                prompt = str(item.get("prompt") or "")
                answer = str(item.get("answer") or "")
                if "页" in prompt or "page" in prompt.lower() or "页" in answer or "page" in answer.lower():
                    hints.append(answer)

    for text in hints:
        if not text:
            continue
        range_match = re.search(r"(\d{1,2})\s*[-~—]\s*(\d{1,2})", text)
        if range_match:
            low = int(range_match.group(1))
            high = int(range_match.group(2))
            return max(5, min(20, (low + high) // 2))
        single_match = re.search(r"(\d{1,2})\s*(?:页|pages?)", text, flags=re.IGNORECASE)
        if single_match:
            return max(5, min(20, int(single_match.group(1))))
    return 8


def clarification_summary(clarification: dict[str, Any] | None) -> str:
    if not isinstance(clarification, dict):
        return ""
    lines: list[str] = []
    questions = clarification.get("questions", [])
    if not isinstance(questions, list):
        return ""
    for item in questions:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if prompt and answer:
            lines.append(f"{prompt}：{answer}")
    return "\n".join(lines)


def _build_stub_skeleton(topic: str, pages: int) -> dict[str, Any]:
    base = [
        ("问题背景与目标", "说明为什么要关注该主题，以及本次演示希望达成的目标"),
        ("现状分析与核心挑战", "梳理当前状态、主要矛盾和需要解决的问题"),
        ("方案思路与总体框架", "给出解决路径、关键模块和逻辑关系"),
        ("关键能力与实现路径", "展开说明支撑方案成立的核心能力或方法"),
        ("案例场景与应用价值", "结合典型场景说明方案如何产生实际价值"),
        ("实施计划与里程碑", "说明落地步骤、阶段成果和协作节奏"),
        ("风险边界与应对策略", "提前说明不确定性、限制条件和应对办法"),
        ("总结结论与下一步行动", "收束核心结论，并给出后续行动建议"),
    ]

    slides: list[dict[str, Any]] = []
    for idx in range(pages):
        if idx < len(base):
            title, intent = base[idx]
        else:
            title = f"补充专题 {idx + 1}"
            intent = "补充说明前面结构中尚未覆盖但对听众理解有帮助的内容"
        slides.append(
            {
                "slide_id": f"s{idx + 1}",
                "title": f"{title}：{topic}" if idx == 0 else title,
                "intent": intent,
                "user_notes": None,
                "chapter_id": None,
            }
        )

    chapters = _build_stub_chapters(slides)

    return {"slides": slides, "chapters": chapters}


def _build_stub_chapters(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not slides:
        return []

    chapter_defs = [
        ("背景与目标", "问题背景、目标设定", 2),
        ("现状与分析", "现状梳理、挑战分析", 2),
        ("方案与路径", "解决思路、实施路径", 2),
        ("总结与展望", "结论、风险、行动建议", 2),
    ]

    chapters: list[dict[str, Any]] = []
    slide_idx = 0
    ch_num = 1
    for title, intent_hint, default_size in chapter_defs:
        if slide_idx >= len(slides):
            break
        remaining = len(slides) - slide_idx
        size = min(default_size, remaining)
        if ch_num == len(chapter_defs) or remaining <= size + 1:
            size = remaining
        chapter_slides = slides[slide_idx : slide_idx + size]
        chapter = {
            "chapter_id": f"ch{ch_num}",
            "title": title,
            "slide_ids": [str(s["slide_id"]) for s in chapter_slides],
        }
        for s in chapter_slides:
            s["chapter_id"] = chapter["chapter_id"]
        chapters.append(chapter)
        slide_idx += size
        ch_num += 1
    return chapters


def _skeleton_prompt(task: dict[str, Any], topic: str, pages: int) -> str:
    input_payload = task.get("input", {}) if isinstance(task.get("input"), dict) else {}
    clarification = task.get("clarification") if isinstance(task.get("clarification"), dict) else None
    summary = clarification_summary(clarification) or "无"
    raw_notes = str(input_payload.get("raw_notes") or "").strip() or "无"
    audience = str(input_payload.get("audience") or "").strip() or "未指定"
    duration = input_payload.get("duration_minutes") or "未指定"
    source_type = str(input_payload.get("source_type") or "short_topic")
    doc_profile = input_payload.get("document_profile") if isinstance(input_payload.get("document_profile"), dict) else {}
    doc_summary = ""
    if doc_profile:
        key_points = doc_profile.get("key_points", [])
        keywords = doc_profile.get("keywords", [])
        doc_summary = f"\n长文档要点：{key_points}\n关键词：{keywords}"

    return f"""你是资深 PPT 策划顾问。请根据用户需求生成可编辑的页级骨架和章节结构，不要生成每页正文要点。

只输出一个 JSON 对象，结构必须如下：
{{
  "chapters": [
    {{
      "chapter_id": "ch1",
      "title": "章节标题（如：背景分析）",
      "slide_ids": ["s1", "s2"]
    }}
  ],
  "slides": [
    {{
      "slide_id": "s1",
      "title": "页面标题",
      "intent": "本页要回答的问题或承担的叙事功能",
      "user_notes": "给后续按页生成的补充要求，可为空字符串"
    }}
  ]
}}

硬性要求：
1) slides 必须正好 {pages} 页；
2) slide_id 必须依次为 s1, s2, ...；
3) chapters 必须至少 2 个，至多 5 个；每个 slide 必须且仅属于一个 chapter；
4) slide_ids 中的 id 必须与 slides 中实际存在的 slide_id 完全一致；
5) title 要具体、有信息量，不要只写"背景/方案/总结"；
6) intent 应说明该页在整套 PPT 中的作用；
7) user_notes 只放后续生成需要注意的约束，没有则输出空字符串；
8) 不要输出 bullets、speaker_notes、evidence 或 Markdown。

用户主题：{topic}
听众/场景：{audience}
演示时长：{duration} 分钟
输入类型：{source_type}
补充材料：{raw_notes}
澄清结果：
{summary}{doc_summary}
""".strip()


def _extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise RuntimeError("LLM returned empty skeleton content.")
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
    raise RuntimeError("LLM skeleton output is not a JSON object.")


def _normalize_skeleton(raw: dict[str, Any], topic: str, pages: int) -> dict[str, Any]:
    slides_in = raw.get("slides", []) if isinstance(raw.get("slides", []), list) else []
    chapters_in = raw.get("chapters", []) if isinstance(raw.get("chapters", []), list) else []
    fallback = _build_stub_skeleton(topic, pages)
    fallback_slides = fallback["slides"] if isinstance(fallback, dict) else []
    fallback_chapters = fallback.get("chapters", []) if isinstance(fallback, dict) else []

    slides: list[dict[str, Any]] = []
    for idx, slide in enumerate(slides_in[:pages], start=1):
        if not isinstance(slide, dict):
            continue
        fb_slide = fallback_slides[idx - 1] if idx - 1 < len(fallback_slides) else {}
        title = str(slide.get("title") or fb_slide.get("title", "")).strip() or fb_slide.get("title", "")
        intent = str(slide.get("intent") or fb_slide.get("intent", "")).strip() or fb_slide.get("intent", "")
        raw_notes = slide.get("user_notes")
        user_notes = "" if raw_notes is None else str(raw_notes).strip()
        slides.append(
            {
                "slide_id": f"s{idx}",
                "title": title,
                "intent": intent,
                "user_notes": user_notes,
                "chapter_id": None,
            }
        )

    while len(slides) < pages:
        fb_slide = fallback_slides[len(slides)] if len(slides) < len(fallback_slides) else {"title": f"补充专题 {len(slides)+1}", "intent": ""}
        slides.append(
            {
                "slide_id": f"s{len(slides)+1}",
                "title": str(fb_slide.get("title", "")),
                "intent": str(fb_slide.get("intent", "")),
                "user_notes": fb_slide.get("user_notes") or "",
                "chapter_id": None,
            }
        )

    slide_id_set = {s["slide_id"] for s in slides}

    if chapters_in:
        valid_chapters: list[dict[str, Any]] = []
        seen_ch_ids: set[str] = set()
        for ch in chapters_in:
            if not isinstance(ch, dict):
                continue
            ch_id = str(ch.get("chapter_id") or "")
            if not ch_id or ch_id in seen_ch_ids:
                continue
            ch_slide_ids = [
                str(sid) for sid in (ch.get("slide_ids") or [])
                if str(sid) in slide_id_set
            ]
            if not ch_slide_ids:
                continue
            seen_ch_ids.add(ch_id)
            ch_title = str(ch.get("title") or "").strip() or ch_id
            valid_chapters.append({
                "chapter_id": ch_id,
                "title": ch_title,
                "slide_ids": ch_slide_ids,
            })
            for s in slides:
                if s["slide_id"] in ch_slide_ids:
                    s["chapter_id"] = ch_id
        if valid_chapters:
            return {"slides": slides, "chapters": valid_chapters}

    result = _build_stub_chapters(slides)
    return {"slides": slides, "chapters": result}


def _build_real_skeleton(task: dict[str, Any], topic: str, pages: int) -> dict[str, Any]:
    if not settings.openai_api_key:
        return _build_stub_skeleton(topic, pages)

    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "你是严谨的JSON生成器。"},
            {"role": "user", "content": _skeleton_prompt(task, topic, pages)},
        ],
        "temperature": 0.3,
        "timeout": settings.llm_timeout_seconds,
    }
    try:
        response = client.chat.completions.create(response_format={"type": "json_object"}, **payload)
    except Exception:
        response = client.chat.completions.create(**payload)

    raw = _extract_json_object(response.choices[0].message.content or "{}")
    return _normalize_skeleton(raw, topic, pages)


def generate_outline_skeleton(task: dict[str, Any]) -> dict[str, Any]:
    """Generate a page-level skeleton with LLM when configured, ready for user editing.
    Returns dict with 'slides' and 'chapters' keys."""

    input_payload = task.get("input", {}) if isinstance(task.get("input"), dict) else {}
    topic = str(input_payload.get("topic") or "演示主题").strip() or "演示主题"
    raw_notes = input_payload.get("raw_notes")
    clarification = task.get("clarification") if isinstance(task.get("clarification"), dict) else None
    pages = infer_target_pages(clarification=clarification, raw_notes=raw_notes if isinstance(raw_notes, str) else None)

    if settings.use_real_llm:
        return _build_real_skeleton(task, topic, pages)
    return _build_stub_skeleton(topic, pages)
