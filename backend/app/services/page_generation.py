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

_NOISE_KEYWORDS = {
    "copyright", "©", "all rights reserved", "sitemap", "网站地图",
    "免责声明", "disclaimer", "terms of service", "privacy policy",
    "cookie policy", "了解更多", "点击这里", "更多详情", "友情链接",
}

_NOISE_LINE = re.compile(r"^[\s>→/|·•\-—]+$")
_NAV_LINE = re.compile(
    r"((首页|关于我们|联系我们|登录|注册|搜索|返回首页|末页)\s*[>→/|]\s*)+(首页|关于我们|联系我们|登录|注册|搜索|返回首页|末页)"
)
_FACT_INDICATORS = re.compile(
    r"[\d.%]+|[A-Z][a-z]{2,}|\"[^\"]{3,}\"|《[^》]+》|是|可|能|会|将|已|应|需要|例如|包括|增加|减少|提升|下降|增长|降低|提高|发展|促进|影响|表明|发现|报告|指出|提出|认为|建议|统计|根据|研究|数据|结果",
)


def clean_evidence_snippet(snippet: str, max_chars: int = 200) -> str:
    """清洗证据片段：去噪声、保留事实句、截断到 max_chars。"""
    text = " ".join((snippet or "").split())
    if not text:
        return ""

    if _NOISE_LINE.search(text):
        return ""
    if _NAV_LINE.search(text):
        return ""
    text_lower = text.lower()
    if any(kw in text_lower for kw in _NOISE_KEYWORDS):
        return ""

    sentences = re.split(r"[。！？\.\!\?]+", text)
    facts = [s.strip() for s in sentences if s.strip() and _FACT_INDICATORS.search(s)]
    if facts:
        text = "。".join(facts[:3])

    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = max(truncated.rfind("。"), truncated.rfind("."), truncated.rfind("！"), truncated.rfind("?"))
    if last_period > max_chars // 2:
        truncated = truncated[:last_period + 1]
    return truncated


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
) -> dict[str, list[dict]]:
    """Retrieve evidence for all pages with bounded concurrency and Tavily budget."""
    retriever = get_retriever(
        documents_dir=settings.retrieval_documents_dir,
        chroma_persist_dir=settings.retrieval_chroma_dir,
        tavily_api_key=(settings.tavily_api_key or "") if settings.retrieval_tavily_enabled else "",
    )
    clarification_text = _clarification_text(clarification)
    depth = RetrievalDepth(retrieval_depth)
    tavily_max = settings.retrieval_tavily_max_pages if settings.retrieval_tavily_enabled else 0
    tavily_used = 0

    by_slide: dict[str, list[dict]] = {}

    async def _run():
        nonlocal tavily_used
        semaphore = asyncio.Semaphore(max(1, settings.retrieval_parallel_pages))
        tavily_lock = asyncio.Lock()

        async def _retrieve_one(slide: dict) -> tuple[str, list[dict]]:
            nonlocal tavily_used
            slide_id = str(slide.get("slide_id") or "")
            query = _build_page_query(topic, slide, clarification_text)
            async with tavily_lock:
                use_web = bool(settings.tavily_api_key) and (
                    settings.retrieval_tavily_enabled
                    and (tavily_max == 0 or tavily_used < tavily_max)
                )
                if use_web and tavily_max > 0:
                    tavily_used += 1
            local_depth = depth if use_web else RetrievalDepth("L0")
            result = await retriever.retrieve(RetrievalRequest(query=query, depth=local_depth))
            selected: list[dict] = []
            for hit in result.hits:
                selected.append(hit.model_dump())
                if len(selected) >= 3:
                    break
            return slide_id, selected

        async def _bounded(slide: dict) -> tuple[str, list[dict]]:
            async with semaphore:
                return await _retrieve_one(slide)

        results = await asyncio.gather(*[_bounded(slide) for slide in skeleton])
        for slide_id, selected in results:
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
    for idx, ev in enumerate(evidence_hits, start=1):
        eid = str(ev.get("evidence_id") or "")
        raw_snippet = str(ev.get("snippet") or "")
        snippet = clean_evidence_snippet(raw_snippet, max_chars=200)
        if not snippet:
            continue
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

## 参考资料（证据 ID 如 {evidence_hits[0].get('evidence_id', 'ev_X') if evidence_hits else 'ev_X'} 等，选择相关度最高的 0-1 条填入）
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
2) 每个 bullet 可引用 0-1 条证据，仅在内容确实来自某条参考资料时引用，与内容无关的证据不要引用；
3) bullet 与证据的匹配依据是语义相关性，不是顺序；
4) 不要输出 Markdown，不要输出解释文字，只输出 JSON。"""


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
        # Only keep evidence_ids that actually exist in the provided hits
        valid_ids = {str(h.get("evidence_id") or "") for h in evidence_hits if h.get("evidence_id")}
        eids = [str(e) for e in eids if str(e) in valid_ids]
        bullets.append({
            "bullet_id": str(bullet.get("bullet_id") or f"{slide_id}-b{jdx}"),
            "text": str(bullet.get("text") or "待补充要点"),
            "evidence_ids": eids[:1],  # 0-1 per bullet
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


def match_bullets_to_evidence(
    bullets: list[dict],
    evidence_hits: list[dict],
    min_score: float = 0.3,
) -> tuple[list[dict], int]:
    """用关键词重叠 + 分数阈值匹配 bullet 与 evidence，返回 (更新后的bullets, low_confidence_count)。"""
    if not evidence_hits:
        return bullets, len(bullets)

    low_count = 0

    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        if bullet.get("evidence_ids"):
            continue  # LLM already matched

        bullet_text = str(bullet.get("text") or "")
        if not bullet_text.strip():
            low_count += 1
            continue

        chars = set(bullet_text)
        has_spaces = " " in bullet_text
        is_english = has_spaces and sum(1 for c in bullet_text if c.isascii() and c.isalpha()) > len(bullet_text) * 0.5
        best_score = 0.0
        best_eid = ""

        _STOPWORDS = {"a", "an", "the", "in", "on", "at", "of", "to", "for", "and", "or", "is", "are", "was", "were", "be", "been", "has", "have", "it", "its", "this", "that", "with", "from", "by", "as", "can", "will", "not", "but", "we", "they", "their", "our"}
        for ev in evidence_hits:
            snippet = str(ev.get("snippet") or "")
            if not snippet:
                continue
            if is_english:
                b_words = set(bullet_text.lower().split()) - _STOPWORDS
                s_words = set(snippet.lower().split()) - _STOPWORDS
                if not b_words or not s_words:
                    continue
                overlap = len(b_words & s_words) / max(1, len(b_words | s_words))
            else:
                snippet_chars = set(snippet)
                if not chars or not snippet_chars:
                    continue
                overlap = len(chars & snippet_chars) / max(1, len(chars | snippet_chars))
            if overlap == 0:
                continue
            ev_score = float(ev.get("score") or 0.5)
            combined = 0.7 * overlap + 0.3 * max(0.0, min(1.0, ev_score))
            if combined > best_score:
                best_score = combined
                best_eid = str(ev.get("evidence_id") or "")

        if best_eid and best_score >= min_score:
            bullet["evidence_ids"] = [best_eid]
        else:
            low_count += 1

    return bullets, low_count


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
        hits = retrieval_by_slide.get(slide_id, [])
        bullets = page.get("bullets", [])
        low_confidence = 0
        if isinstance(bullets, list):
            bullets, low_confidence = match_bullets_to_evidence(bullets, hits)
            page["bullets"] = bullets
        slides.append(page)

        # Collect evidence for this page (with cleaning)
        added_count = 0
        for hit in hits:
            raw_snippet = str(hit.get("snippet") or "")
            cleaned = clean_evidence_snippet(raw_snippet, max_chars=200)
            if not cleaned:
                continue
            evidence_catalog.append({
                "evidence_id": str(hit.get("evidence_id") or ""),
                "snippet": cleaned,
                "source_id": str(hit.get("source_id") or "unknown"),
                "locator": str(hit.get("locator") or ""),
                "score": hit.get("score"),
                "confidence": hit.get("confidence"),
            })
            added_count += 1
        coverage_total += added_count

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
            "low_confidence_bullets": sum(
                1 for s in slides
                for b in (s.get("bullets", []) if isinstance(s.get("bullets"), list) else [])
                if isinstance(b, dict) and not b.get("evidence_ids")
            ),
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

    def _update(
        phase: str,
        current: int | None,
        total: int | None,
        message: str,
        percent: int | None = None,
        slide_id: str | None = None,
        completed: int | None = None,
        failed: int | None = None,
    ) -> None:
        task["progress"] = {
            "phase": phase,
            "current": current,
            "total": total,
            "message": message,
            "percent": percent,
            "slide_id": slide_id,
            "completed": completed,
            "failed": failed,
        }
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        if on_progress:
            on_progress(task)

    total = len(skeleton)

    def _refresh_partial_outline(
        page_results: dict[str, dict],
        completed_pages: int,
        failed_pages: int,
    ) -> None:
        completed_slide_ids = set(page_results.keys())
        partial_skeleton = [
            slide
            for slide in skeleton
            if str(slide.get("slide_id") or "") in completed_slide_ids
        ]

        partial_outline = merge_pages_to_outline(
            topic,
            partial_skeleton,
            page_results,
            retrieval_by_slide,
            retrieval_depth,
        )
        partial_outline["meta"]["partial"] = True
        partial_outline["meta"]["completed_pages"] = completed_pages
        partial_outline["meta"]["failed_pages"] = failed_pages
        partial_outline["meta"]["total_pages"] = total

        task["outline"] = partial_outline

    # Phase 1: retrieve evidence for all pages
    _update("retrieving_page", 0, total, "正在检索相关资料...", 0)
    retrieval_by_slide = retrieve_for_pages(topic, retrieval_depth, skeleton, clarification)

    # Assign evidence IDs
    ev_counter = 1
    for slide_id, hits in retrieval_by_slide.items():
        for hit in hits:
            hit["evidence_id"] = f"ev_{ev_counter}"
            ev_counter += 1

    task["outline"] = {
        "title": topic,
        "slides": [],
        "evidence_catalog": [],
        "page_evidence_map": [],
        "meta": {
            "retrieval_depth": retrieval_depth,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "page_targeted",
            "model": settings.llm_model,
            "schema_version": settings.outline_schema_version,
            "retrieval_enabled": True,
            "partial": True,
            "completed_pages": 0,
            "failed_pages": 0,
            "total_pages": total,
        },
    }
    _update(
        "llm_page",
        0,
        total,
        "正在生成页面内容...",
        0,
        completed=0,
        failed=0,
    )

    # Phase 2: generate each page with concurrency control
    page_results: dict[str, dict] = {}
    processed_pages = 0
    completed_pages = 0
    failed_pages = 0

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
                page = future.result()
                page["generation_status"] = "done"
                page_results[slide_id] = page
                completed_pages += 1
            except Exception as exc:
                logger.exception("Page generation failed for slide=%s", slide_id)
                page = _stub_page(slide)
                page["generation_status"] = "failed"
                page["error"] = {
                    "code": "PAGE_GENERATION_FAILED",
                    "message": str(exc),
                }
                page_results[slide_id] = page
                failed_pages += 1

            processed_pages += 1
            pct = int(processed_pages / total * 100) if total else None

            _refresh_partial_outline(
                page_results,
                completed_pages,
                failed_pages,
            )

            _update(
                "llm_page",
                processed_pages,
                total,
                f"已完成 {completed_pages} 页，失败 {failed_pages} 页，正在生成第 {processed_pages}/{total} 页内容...",
                pct,
                slide_id=slide_id,
                completed=completed_pages,
                failed=failed_pages,
            )

    # Phase 3: merge
    _update(
        "assembling",
        total,
        total,
        "正在合并各页内容...",
        100,
        completed=completed_pages,
        failed=failed_pages,
    )

    outline = merge_pages_to_outline(topic, skeleton, page_results, retrieval_by_slide, retrieval_depth)
    outline["meta"]["partial"] = False
    outline["meta"]["completed_pages"] = completed_pages
    outline["meta"]["failed_pages"] = failed_pages
    outline["meta"]["total_pages"] = total
    task["outline"] = outline

    # Phase 4: saving
    _update(
        "saving",
        total,
        total,
        "正在保存完整大纲...",
        100,
        completed=completed_pages,
        failed=failed_pages,
    )

    return outline
