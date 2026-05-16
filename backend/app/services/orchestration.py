from __future__ import annotations

import asyncio
import re
from typing import Any

from app.config import settings
from app.retrieval import RetrievalDepth, RetrievalRequest, get_retriever
from app.services.generation import generate_outline

_RETRIEVAL_INTENT = re.compile(
    r"(检索|引用|资料来源|证据来源|需要.*来源|cite|retriev|rag\b|web\s*search)",
    re.IGNORECASE,
)


def _infer_target_pages(
    clarification: dict[str, Any] | None,
    raw_notes: str | None,
) -> int:
    default_pages = 8
    hints: list[str] = []
    if isinstance(raw_notes, str):
        hints.append(raw_notes)
    if clarification and isinstance(clarification, dict):
        questions = clarification.get("questions", [])
        if isinstance(questions, list):
            for item in questions:
                if not isinstance(item, dict):
                    continue
                prompt = str(item.get("prompt") or "")
                answer = str(item.get("answer") or "")
                if "页" in prompt or "page" in prompt.lower():
                    hints.append(answer)
                else:
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
    return default_pages


def _normalize_depth(value: Any) -> str:
    if isinstance(value, str):
        upper = value.upper().strip()
        if upper in ("L0", "L1", "L2"):
            return upper
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        upper = enum_value.upper().strip()
        if upper in ("L0", "L1", "L2"):
            return upper
    return "L1"


def _clarification_text(clarification: dict[str, Any] | None) -> str:
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


def _collect_user_text(clarification: dict[str, Any] | None, raw_notes: str | None) -> list[str]:
    texts: list[str] = []
    if isinstance(raw_notes, str) and raw_notes.strip():
        texts.append(raw_notes.strip())
    if clarification and isinstance(clarification, dict):
        questions = clarification.get("questions", [])
        if isinstance(questions, list):
            for item in questions:
                if isinstance(item, dict):
                    answer = str(item.get("answer") or "").strip()
                    if answer:
                        texts.append(answer)
    return texts


def _user_requests_retrieval(clarification: dict[str, Any] | None, raw_notes: str | None) -> bool:
    return any(_RETRIEVAL_INTENT.search(text) for text in _collect_user_text(clarification, raw_notes))


def _build_retrieval_query(
    topic: str,
    slide_title: str,
    clarification_text: str,
    segment_context: str = "",
) -> str:
    parts = [topic, f"页面目标：{slide_title}"]
    if segment_context:
        parts.append(f"文档片段：{segment_context}")
    if clarification_text:
        parts.append(f"补充约束：{clarification_text}")
    return "\n".join(parts).strip()


def _segment_context_for_slide(segments: list[str], slide_idx: int) -> str:
    if not segments:
        return ""
    segment = segments[slide_idx % len(segments)]
    return segment[:400].strip()


def _next_depth(retrieval_depth: str) -> str:
    if retrieval_depth == "L0":
        return "L1"
    if retrieval_depth == "L1":
        return "L2"
    return "L2"


def _default_slide_titles(target_pages: int) -> list[str]:
    """Deterministic slide goals used before grounded generation."""
    base = [
        "问题背景与目标",
        "现状分析与关键挑战",
        "方案设计与核心路径",
        "实施计划与里程碑",
        "风险边界与应对策略",
        "投入产出与预期收益",
        "组织协同与落地保障",
        "结论与下一步行动",
    ]
    pages = max(5, min(20, int(target_pages)))
    if pages <= len(base):
        return base[:pages]
    titles = list(base)
    while len(titles) < pages:
        titles.append(f"补充专题 {len(titles) + 1}")
    return titles


def _source_trust_score(source_id: str) -> float:
    sid = (source_id or "").lower()
    if any(tag in sid for tag in ("gov", "edu", "official", "who", "un", "oecd", "imf", "worldbank")):
        return 1.0
    if any(tag in sid for tag in ("report", "journal", "paper", "research", "statista", "mckinsey", "gartner")):
        return 0.8
    if any(tag in sid for tag in ("blog", "forum", "weibo", "post")):
        return 0.4
    return 0.6


def _hit_quality(hit: dict[str, Any]) -> float:
    score = hit.get("score")
    confidence = hit.get("confidence")
    score_v = float(score) if isinstance(score, (int, float)) else 0.5
    conf_v = float(confidence) if isinstance(confidence, (int, float)) else 0.5
    trust_v = _source_trust_score(str(hit.get("source_id") or ""))
    return 0.5 * score_v + 0.25 * conf_v + 0.25 * trust_v


def _summarize_document_text(document_text: str | None) -> str:
    text = (document_text or "").strip()
    if not text:
        return ""
    compact = " ".join(text.split())
    return compact[:1500]


def _build_generation_seed(
    topic: str,
    source_type: str,
    document_text: str | None,
    document_title: str | None,
    raw_notes: str | None,
    document_summary: str | None = None,
    document_segments: list[str] | None = None,
    document_key_points: list[str] | None = None,
    document_keywords: list[str] | None = None,
) -> str:
    if source_type != "long_document":
        return topic

    doc_summary = (document_summary or "").strip() or _summarize_document_text(document_text)
    parts = [f"主题：{topic}"]
    if document_title:
        parts.append(f"文档标题：{document_title}")
    if doc_summary:
        parts.append(f"文档摘要：{doc_summary}")

    segments = [segment.strip() for segment in (document_segments or []) if isinstance(segment, str) and segment.strip()]
    if segments:
        parts.append("文档分段（按顺序）：")
        for idx, segment in enumerate(segments[:8], start=1):
            parts.append(f"  [{idx}] {segment[:420]}")

    key_points = [point.strip() for point in (document_key_points or []) if isinstance(point, str) and point.strip()]
    if key_points:
        parts.append("文档要点：")
        for idx, point in enumerate(key_points[:8], start=1):
            parts.append(f"  - {point[:200]}")

    keywords = [word.strip() for word in (document_keywords or []) if isinstance(word, str) and word.strip()]
    if keywords:
        parts.append(f"关键词：{', '.join(keywords[:12])}")

    if raw_notes:
        parts.append(f"补充备注：{raw_notes}")
    return "\n".join(parts)


def _build_grounded_generation_seed(
    generation_seed: str,
    retrieval_by_slide: dict[str, list[dict[str, Any]]],
) -> str:
    lines: list[str] = [
        generation_seed,
        "",
        "以下是可引用证据（仅允许使用这些证据中的事实，禁止自行新增统计数据或来源）：",
    ]
    for slide_title, hits in retrieval_by_slide.items():
        lines.append(f"- 页面：{slide_title}")
        if not hits:
            lines.append("  - 无可用证据")
            continue
        for idx, hit in enumerate(hits[:3], start=1):
            snippet = str(hit.get("snippet") or "").replace("\n", " ").strip()
            source_id = str(hit.get("source_id") or "unknown").strip()
            locator = str(hit.get("locator") or "").strip()
            lines.append(f"  - 证据{idx}: {snippet}（来源: {source_id}；定位: {locator}）")
    lines.append("")
    lines.append("写作约束：若证据不足，请使用定性表达，不要编造具体数字、年份、机构结论。")
    return "\n".join(lines)


def _strip_unverified_evidence(outline: dict[str, Any]) -> dict[str, Any]:
    """Remove LLM-provided evidence to prevent fabricated citations."""
    slides = outline.get("slides", [])
    if isinstance(slides, list):
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            bullets = slide.get("bullets", [])
            if not isinstance(bullets, list):
                continue
            for bullet in bullets:
                if not isinstance(bullet, dict):
                    continue
                bullet["evidence_ids"] = []
    outline["evidence_catalog"] = []
    return outline


def _should_retrieve(
    retrieval_depth: str,
    clarification: dict[str, Any] | None,
    raw_notes: str | None,
    source_type: str = "short_topic",
    document_profile: dict[str, Any] | None = None,
) -> bool:
    if retrieval_depth in ("L1", "L2"):
        return True
    if _user_requests_retrieval(clarification=clarification, raw_notes=raw_notes):
        return True
    if raw_notes and len(raw_notes.strip()) < 80:
        return True
    if source_type == "long_document":
        profile = document_profile if isinstance(document_profile, dict) else {}
        if int(profile.get("char_count", 0)) >= 400:
            return True
    submitted = bool((clarification or {}).get("submitted"))
    return submitted and retrieval_depth == "L0"


def _retrieve_for_slides(
    topic: str,
    retrieval_depth: str,
    slide_titles: list[str],
    clarification: dict[str, Any] | None,
    min_quality_score: float,
    document_segments: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    retriever = get_retriever(
        documents_dir=settings.retrieval_documents_dir,
        chroma_persist_dir=settings.retrieval_chroma_dir,
        tavily_api_key=settings.tavily_api_key or "",
    )
    clarification_text = _clarification_text(clarification)
    segments = [segment.strip() for segment in (document_segments or []) if isinstance(segment, str) and segment.strip()]

    async def _run() -> dict[str, list[dict[str, Any]]]:
        by_slide: dict[str, list[dict[str, Any]]] = {}
        depth = RetrievalDepth(retrieval_depth)
        for slide_idx, slide_title in enumerate(slide_titles):
            segment_context = _segment_context_for_slide(segments, slide_idx) if segments else ""
            query = _build_retrieval_query(
                topic=topic,
                slide_title=slide_title,
                clarification_text=clarification_text,
                segment_context=segment_context,
            )
            result = await retriever.retrieve(RetrievalRequest(query=query, depth=depth))
            selected: list[dict[str, Any]] = []
            for hit in result.hits:
                payload = hit.model_dump()
                payload["quality"] = _hit_quality(payload)
                if payload["quality"] >= min_quality_score:
                    selected.append(payload)
                if len(selected) >= 3:
                    break
            by_slide[slide_title] = selected
        return by_slide

    return asyncio.run(_run())


def _inject_evidence(
    outline: dict[str, Any],
    retrieval_by_slide: dict[str, list[dict[str, Any]]],
    min_evidence_per_slide: int,
) -> dict[str, Any]:
    slides = outline.get("slides", [])
    if not isinstance(slides, list):
        return outline

    evidence_catalog: list[dict[str, Any]] = []
    next_id = 1
    coverage_total = 0
    low_confidence_slides: list[str] = []
    retrieval_items = list(retrieval_by_slide.items())
    for slide_idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        title = str(slide.get("title") or "")
        hits = retrieval_by_slide.get(title, [])
        if not hits and slide_idx < len(retrieval_items):
            # Fallback: when LLM rewrites slide titles, keep evidence aligned by page order.
            _, hits = retrieval_items[slide_idx]
        if not hits:
            low_confidence_slides.append(title)
            continue

        added_ids: list[str] = []
        for hit in hits:
            evidence_id = f"ev_{next_id}"
            next_id += 1
            evidence_catalog.append(
                {
                    "evidence_id": evidence_id,
                    "snippet": str(hit.get("snippet") or ""),
                    "source_id": str(hit.get("source_id") or "unknown"),
                    "locator": str(hit.get("locator") or ""),
                    "score": hit.get("score"),
                    "confidence": hit.get("confidence"),
                }
            )
            added_ids.append(evidence_id)
        coverage_total += len(added_ids)

        bullets = slide.get("bullets", [])
        if isinstance(bullets, list):
            for idx, bullet in enumerate(bullets):
                if not isinstance(bullet, dict):
                    continue
                if bullet.get("evidence_ids"):
                    continue
                if added_ids:
                    bullet["evidence_ids"] = [added_ids[min(idx, len(added_ids) - 1)]]
        if len(added_ids) < min_evidence_per_slide:
            low_confidence_slides.append(title)

    outline["evidence_catalog"] = evidence_catalog
    meta = outline.get("meta", {})
    if isinstance(meta, dict):
        meta["research_mode"] = "page_targeted"
        meta["retrieval_enabled"] = True
        meta["evidence_coverage_total"] = coverage_total
        meta["low_confidence_slides"] = low_confidence_slides
        outline["meta"] = meta
    return outline


def _validate_evidence_integrity(outline: dict[str, Any]) -> dict[str, Any]:
    catalog = outline.get("evidence_catalog", [])
    valid_ids = {
        str(item.get("evidence_id"))
        for item in catalog
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }

    orphaned = 0
    slides = outline.get("slides", [])
    if isinstance(slides, list):
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            bullets = slide.get("bullets", [])
            if not isinstance(bullets, list):
                continue
            for bullet in bullets:
                if not isinstance(bullet, dict):
                    continue
                raw_ids = bullet.get("evidence_ids", [])
                if not isinstance(raw_ids, list):
                    bullet["evidence_ids"] = []
                    continue
                cleaned = [ev_id for ev_id in raw_ids if isinstance(ev_id, str) and ev_id in valid_ids]
                orphaned += len(raw_ids) - len(cleaned)
                bullet["evidence_ids"] = cleaned

    meta = outline.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    # True when no dangling evidence_ids remain after cleanup (removed count is separate).
    meta["evidence_integrity_ok"] = True
    meta["evidence_orphaned_refs_removed"] = orphaned
    outline["meta"] = meta
    return outline


def _fallback_deepen_for_sparse_slides(
    topic: str,
    retrieval_depth: str,
    slide_titles: list[str],
    clarification: dict[str, Any] | None,
    min_evidence_per_slide: int,
    min_quality_score: float,
    retrieval_by_slide: dict[str, list[dict[str, Any]]],
    document_segments: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    sparse = [title for title in slide_titles if len(retrieval_by_slide.get(title, [])) < min_evidence_per_slide]
    if not sparse:
        return retrieval_by_slide

    deeper_depth = _next_depth(retrieval_depth)
    deeper = _retrieve_for_slides(
        topic=topic,
        retrieval_depth=deeper_depth,
        slide_titles=sparse,
        clarification=clarification,
        min_quality_score=min_quality_score,
        document_segments=document_segments,
    )
    merged = dict(retrieval_by_slide)
    for title, hits in deeper.items():
        existing = merged.get(title, [])
        merged[title] = (existing + hits)[:3]
    return merged


def generate_outline_with_research(
    topic: str,
    retrieval_depth: str,
    clarification: dict[str, Any] | None = None,
    raw_notes: str | None = None,
    source_type: str = "short_topic",
    document_text: str | None = None,
    document_title: str | None = None,
    document_summary: str | None = None,
    document_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retrieval_depth = _normalize_depth(retrieval_depth)
    profile = document_profile if isinstance(document_profile, dict) else {}
    document_segments = profile.get("segments") if isinstance(profile.get("segments"), list) else []
    document_key_points = profile.get("key_points") if isinstance(profile.get("key_points"), list) else []
    document_keywords = profile.get("keywords") if isinstance(profile.get("keywords"), list) else []

    target_pages = _infer_target_pages(clarification=clarification, raw_notes=raw_notes)
    generation_seed = _build_generation_seed(
        topic=topic,
        source_type=source_type,
        document_text=document_text,
        document_title=document_title,
        raw_notes=raw_notes,
        document_summary=document_summary or str(profile.get("summary") or ""),
        document_segments=document_segments,
        document_key_points=document_key_points,
        document_keywords=document_keywords,
    )

    if not _should_retrieve(
        retrieval_depth=retrieval_depth,
        clarification=clarification,
        raw_notes=raw_notes,
        source_type=source_type,
        document_profile=profile,
    ):
        outline = generate_outline(topic=generation_seed, retrieval_depth=retrieval_depth, target_pages=target_pages)
        outline = _strip_unverified_evidence(outline)
        meta = outline.get("meta", {})
        if isinstance(meta, dict):
            meta["retrieval_enabled"] = False
            meta["research_mode"] = "generation_only"
            outline["meta"] = meta
        return outline

    slide_titles = _default_slide_titles(target_pages=target_pages)
    min_evidence_per_slide = max(1, settings.retrieval_min_evidence_per_slide)
    min_quality_score = max(0.0, min(1.0, settings.retrieval_min_quality_score))

    retrieval_by_slide = _retrieve_for_slides(
        topic=generation_seed,
        retrieval_depth=retrieval_depth,
        slide_titles=slide_titles,
        clarification=clarification,
        min_quality_score=min_quality_score,
        document_segments=document_segments,
    )
    if settings.retrieval_enable_fallback_deepen:
        retrieval_by_slide = _fallback_deepen_for_sparse_slides(
            topic=generation_seed,
            retrieval_depth=retrieval_depth,
            slide_titles=slide_titles,
            clarification=clarification,
            min_evidence_per_slide=min_evidence_per_slide,
            min_quality_score=min_quality_score,
            retrieval_by_slide=retrieval_by_slide,
            document_segments=document_segments,
        )

    grounded_seed = _build_grounded_generation_seed(
        generation_seed=generation_seed,
        retrieval_by_slide=retrieval_by_slide,
    )
    outline = generate_outline(
        topic=grounded_seed,
        retrieval_depth=retrieval_depth,
        target_pages=target_pages,
    )
    outline = _strip_unverified_evidence(outline)

    enriched = _inject_evidence(
        outline=outline,
        retrieval_by_slide=retrieval_by_slide,
        min_evidence_per_slide=min_evidence_per_slide,
    )
    return _validate_evidence_integrity(enriched)
