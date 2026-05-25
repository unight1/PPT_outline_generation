from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable

from openai import OpenAI

from app.config import settings
from app.retrieval import RetrievalDepth, RetrievalRequest, get_retriever

logger = logging.getLogger(__name__)


def _build_page_query(topic: str, slide: dict, clarification_text: str) -> str:
    parts = [topic]
    title = str(slide.get("title") or "")
    if title:
        parts.append(f"页面目标：{title}")
    intent = str(slide.get("intent") or "")
    if intent:
        parts.append(f"本页意图：{intent}")
    notes = str(slide.get("user_notes") or "")
    if notes:
        parts.append(f"用户备注：{notes}")
    if clarification_text:
        parts.append(f"补充约束：{clarification_text}")
    return "\n".join(parts)


def _clarification_text(clarification: dict | None) -> str:
    if not clarification:
        return ""
    items = clarification.get("questions", [])
    if not isinstance(items, list):
        return ""
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if prompt and answer:
            lines.append(f"{prompt}：{answer}")
    return "\n".join(lines)


def retrieve_for_pages(
    topic: str,
    retrieval_depth: str,
    skeleton: list[dict],
    clarification: dict | None,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Retrieve evidence for all pages. Returns (by_slide, all_evidence_catalog)."""
    retriever = get_retriever(
        documents_dir=settings.retrieval_documents_dir,
        chroma_persist_dir=settings.retrieval_chroma_dir,
        tavily_api_key=settings.tavily_api_key or "",
    )
    clarification_text = _clarification_text(clarification)
    depth = RetrievalDepth(retrieval_depth)

    by_slide: dict[str, list[dict]] = {}

    async def _run():
        for slide in skeleton:
            slide_id = str(slide.get("slide_id") or "")
            query = _build_page_query(topic, slide, clarification_text)
            result = await retriever.retrieve(RetrievalRequest(query=query, depth=depth))
            selected: list[dict] = []
            for hit in result.hits:
                selected.append(hit.model_dump())
                if len(selected) >= 3:
                    break
            by_slide[slide_id] = selected

    asyncio.run(_run())
    return by_slide


def _build_page_prompt(
    topic: str,
    slide: dict,
    evidence_hits: list[dict],
) -> str:
    slide_id = str(slide.get("slide_id") or "")
    slide_title = str(slide.get("title") or "")
    intent = str(slide.get("intent") or "")
    user_notes = str(slide.get("user_notes") or "")

    evidence_lines: list[str] = []
    for ev in evidence_hits:
        eid = ev.get("evidence_id", "")
        snippet = str(ev.get("snippet") or "")[:300]
        source = str(ev.get("source_id") or "unknown")
        evidence_lines.append(f"- {eid}: {snippet}  (来源：{source})")
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "（无参考资料）"

    return f"""你是PPT大纲助手。根据以下信息为指定页面生成bullets和讲者备注。

## 演示主题
{topic}

## 本页信息
- 页面标题：{slide_title}
- 页面意图：{intent or "无"}
- 用户补充要求：{user_notes or "无"}

## 参考资料（可选择引用，在 evidence_ids 中填入对应 ID）
{evidence_block}

## 输出要求
只输出一个JSON对象：
{{
  "bullets": [
    {{"bullet_id": "{slide_id}-b1", "text": "要点内容", "evidence_ids": ["ev_1"]}}
  ],
  "speaker_notes": "讲者备注"
}}

硬性要求：
1) bullets 至少 2 个，最多 6 个；
2) 每个 bullet 可引用 0-1 个 evidence_id，仅在内容确实来自某条证据时引用；
3) 不要输出 Markdown，不要输出解释文字，只输出 JSON。"""


def _extract_json_object(content: str) -> dict:
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


def _generate_single_page(
    topic: str,
    slide: dict,
    evidence_hits: list[dict],
) -> dict:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    prompt = _build_page_prompt(topic, slide, evidence_hits)
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "你是严谨的JSON生成器。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "timeout": settings.llm_timeout_seconds,
    }
    try:
        response = client.chat.completions.create(response_format={"type": "json_object"}, **payload)
    except Exception:
        response = client.chat.completions.create(**payload)

    content = response.choices[0].message.content or "{}"
    raw = _extract_json_object(content)

    slide_id = str(slide.get("slide_id") or "")
    bullets_in = raw.get("bullets", []) if isinstance(raw.get("bullets", []), list) else []
    bullets: list[dict] = []
    for jdx, bullet in enumerate(bullets_in[:6], start=1):
        if not isinstance(bullet, dict):
            continue
        eids = bullet.get("evidence_ids", [])
        if not isinstance(eids, list):
            eids = []
        bullets.append({
            "bullet_id": str(bullet.get("bullet_id") or f"{slide_id}-b{jdx}"),
            "text": str(bullet.get("text") or "待补充要点"),
            "evidence_ids": [str(e) for e in eids],
        })
    if len(bullets) < 2:
        bullets.append({"bullet_id": f"{slide_id}-b{len(bullets)+1}", "text": "待补充要点", "evidence_ids": []})

    return {
        "slide_id": slide_id,
        "title": str(slide.get("title") or slide_id),
        "bullets": bullets,
        "speaker_notes": str(raw.get("speaker_notes") or ""),
    }


def _stub_page(slide: dict) -> dict:
    slide_id = str(slide.get("slide_id") or "")
    return {
        "slide_id": slide_id,
        "title": str(slide.get("title") or slide_id),
        "bullets": [
            {"bullet_id": f"{slide_id}-b1", "text": "待补充要点", "evidence_ids": []},
            {"bullet_id": f"{slide_id}-b2", "text": "待补充要点", "evidence_ids": []},
        ],
        "speaker_notes": "",
    }


def merge_pages_to_outline(
    topic: str,
    skeleton: list[dict],
    page_results: dict[str, dict],
    retrieval_by_slide: dict[str, list[dict]],
    retrieval_depth: str,
) -> dict:
    slides: list[dict] = []
    evidence_catalog: list[dict] = []
    coverage_total = 0

    for slide in skeleton:
        slide_id = str(slide.get("slide_id") or "")
        page = page_results.get(slide_id)
        if page is None:
            page = _stub_page(slide)
        slides.append(page)

        # Collect evidence for this page
        hits = retrieval_by_slide.get(slide_id, [])
        for hit in hits:
            evidence_catalog.append({
                "evidence_id": str(hit.get("evidence_id") or ""),
                "snippet": str(hit.get("snippet") or ""),
                "source_id": str(hit.get("source_id") or "unknown"),
                "locator": str(hit.get("locator") or ""),
                "score": hit.get("score"),
                "confidence": hit.get("confidence"),
            })
        coverage_total += len(hits)

    # Build page_evidence_map
    ev_lookup = {ev["evidence_id"]: ev for ev in evidence_catalog}
    page_evidence_map: list[dict] = []
    for s in slides:
        ev_to_bullets: dict[str, list[str]] = {}
        for bullet in s.get("bullets", []):
            bid = str(bullet.get("bullet_id") or "")
            for eid in bullet.get("evidence_ids", []):
                ev_to_bullets.setdefault(eid, []).append(bid)
        evidence_trace: list[dict] = []
        for eid, bids in ev_to_bullets.items():
            ev = ev_lookup.get(eid)
            if ev:
                entry = dict(ev)
                entry["bullet_ids"] = bids
                evidence_trace.append(entry)
        page_evidence_map.append({
            "slide_id": s["slide_id"],
            "slide_title": s["title"],
            "evidence_trace": evidence_trace,
        })

    return {
        "title": topic,
        "slides": slides,
        "evidence_catalog": evidence_catalog,
        "page_evidence_map": page_evidence_map,
        "meta": {
            "retrieval_depth": retrieval_depth,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "page_targeted",
            "model": settings.llm_model,
            "schema_version": settings.outline_schema_version,
            "retrieval_enabled": True,
            "evidence_coverage_total": coverage_total,
        },
    }


def generate_pages_from_skeleton(
    *,
    task: dict[str, Any],
    concurrency: int = 2,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    input_data = task["input"]
    topic = input_data["topic"]
    retrieval_depth = input_data.get("retrieval_depth", "L1")
    clarification = task.get("clarification")
    skeleton = task.get("outline_skeleton", [])

    if not skeleton or not isinstance(skeleton, list):
        raise RuntimeError("outline_skeleton is empty or invalid")

    def _update(phase: str, current: int | None, total: int | None, message: str, percent: int | None = None) -> None:
        task["progress"] = {
            "phase": phase,
            "current": current,
            "total": total,
            "message": message,
            "percent": percent,
        }
        if on_progress:
            on_progress(task)

    total = len(skeleton)

    # Phase 1: retrieve evidence for all pages
    _update("retrieving_page", 0, total, "正在检索相关资料...", 0)
    retrieval_by_slide = retrieve_for_pages(topic, retrieval_depth, skeleton, clarification)

    # Assign evidence IDs
    ev_counter = 1
    for slide_id, hits in retrieval_by_slide.items():
        for hit in hits:
            hit["evidence_id"] = f"ev_{ev_counter}"
            ev_counter += 1

    # Phase 2: generate each page with concurrency control
    _update("llm_page", 0, total, "正在生成页面内容...", 0)
    page_results: dict[str, dict] = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, total))) as executor:
        futures = {}
        for slide in skeleton:
            slide_id = str(slide.get("slide_id") or "")
            evidence = retrieval_by_slide.get(slide_id, [])
            future = executor.submit(_generate_single_page, topic, slide, evidence)
            futures[future] = (slide_id, slide)

        for future in as_completed(futures):
            slide_id, slide = futures[future]
            try:
                page_results[slide_id] = future.result()
            except Exception:
                logger.exception("Page generation failed for slide=%s", slide_id)
                page_results[slide_id] = _stub_page(slide)
            completed += 1
            pct = int(completed / total * 100) if total else None
            _update("llm_page", completed, total, f"正在生成第 {completed}/{total} 页内容...", pct)

    # Phase 3: merge
    _update("assembling", None, None, "正在合并各页内容...")
    outline = merge_pages_to_outline(topic, skeleton, page_results, retrieval_by_slide, retrieval_depth)

    # Phase 4: saving
    _update("saving", None, None, "正在保存...", 100)
    return outline
