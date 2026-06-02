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

# R3: 低质量来源的 URL 特征（聚合页、营销页、社交媒体聚合等）
_LOW_QUALITY_SOURCE_PATTERNS = re.compile(
    r"(zhidao\.baidu|wenku\.baidu|360doc|mbalib|docin|scribd|slideshare"
    r"|marketing|promo|ads\.|advertis|coupon|shop\.|mall\."
    r"|weibo\.com|tieba\.baidu|zhihu\.com/p/[0-9]"   # 知乎个人博客，非官方
    r"|pinterest|instagram|facebook|twitter\.com"
    r"|aggregat|digest|roundup|listicle)",
    re.IGNORECASE,
)

_HIGH_QUALITY_SOURCE_PATTERNS = re.compile(
    r"(\.gov|\.edu|arxiv\.org|doi\.org|pubmed|nature\.com|science\.org"
    r"|acm\.org|ieee\.org|springer|wiley|elsevier"
    r"|mckinsey|gartner|idc\.com|statista|forrester"
    r"|reuters|bloomberg|ft\.com|wsj\.com|economist"
    r"|github\.com|docs\.|developer\.|api\.)",
    re.IGNORECASE,
)


def _is_low_quality_source(source_id: str) -> bool:
    """R3: 判断来源是否为低质量（聚合页/营销页/社交聚合），返回 True 则降权。"""
    if not source_id:
        return False
    # 高质量来源优先放行
    if _HIGH_QUALITY_SOURCE_PATTERNS.search(source_id):
        return False
    return bool(_LOW_QUALITY_SOURCE_PATTERNS.search(source_id))

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


class SlideWorkflowError(RuntimeError):
    """Raised when slide-level retrieval or LLM fails; mapped to task.error by the API layer."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        slide_id: str | None = None,
        phase: str | None = None,
        retryable: bool = True,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.slide_id = slide_id
        self.phase = phase
        self.retryable = retryable
        self.reason = reason


def _retrieval_cache_key(slide: dict, retrieval_depth: str, tavily_enabled: bool) -> str:
    return "|".join(
        [
            str(slide.get("slide_id") or ""),
            str(slide.get("title") or ""),
            str(slide.get("intent") or ""),
            str(slide.get("user_notes") or ""),
            retrieval_depth,
            "web" if tavily_enabled else "local",
        ]
    )


def _strip_evidence_ids(hits: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        entry = {k: v for k, v in hit.items() if k != "evidence_id"}
        cleaned.append(entry)
    return cleaned


def _classify_retrieval_exception(exc: Exception, slide_id: str) -> SlideWorkflowError:
    if isinstance(exc, SlideWorkflowError):
        return exc
    lowered = str(exc).lower()
    if "timeout" in lowered:
        return SlideWorkflowError(
            "TIMEOUT",
            "检索超时，请稍后重试。",
            slide_id=slide_id,
            phase="retrieving_page",
            reason=str(exc),
        )
    if "tavily" in lowered:
        return SlideWorkflowError(
            "TAVILY_ERROR",
            "网络检索失败，请检查 Tavily 配置或关闭联网检索。",
            slide_id=slide_id,
            phase="retrieving_page",
            reason=str(exc),
        )
    if any(token in lowered for token in ("chroma", "embedding", "retriev", "index")):
        return SlideWorkflowError(
            "RETRIEVAL_ERROR",
            "本地检索失败，请检查文档索引或检索深度。",
            slide_id=slide_id,
            phase="retrieving_page",
            reason=str(exc),
        )
    return SlideWorkflowError(
        "RETRIEVAL_ERROR",
        "检索失败。",
        slide_id=slide_id,
        phase="retrieving_page",
        reason=str(exc),
    )


def _classify_llm_exception(exc: Exception, slide_id: str) -> SlideWorkflowError:
    if isinstance(exc, SlideWorkflowError):
        return exc
    lowered = str(exc).lower()
    if "timeout" in lowered:
        return SlideWorkflowError(
            "TIMEOUT",
            "模型调用超时，请稍后重试。",
            slide_id=slide_id,
            phase="llm_page",
            reason=str(exc),
        )
    return SlideWorkflowError(
        "LLM_ERROR",
        "页面内容生成失败。",
        slide_id=slide_id,
        phase="llm_page",
        reason=str(exc),
    )


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

    # R3: 根据 intent 关键词推断检索需要，追加意图修饰词让 query 更精准
    intent_lower = (intent + " " + title).lower()
    if any(kw in intent_lower for kw in ("数据", "规模", "市场", "统计", "趋势", "增长", "比例", "占比")):
        parts.append("检索需求：需要数据、市场规模、统计数字")
    elif any(kw in intent_lower for kw in ("案例", "实践", "应用", "示例", "example", "case")):
        parts.append("检索需求：需要真实案例或行业实践")
    elif any(kw in intent_lower for kw in ("定义", "概念", "什么是", "原理", "机制", "definition")):
        parts.append("检索需求：需要定义、概念解释或原理说明")
    elif any(kw in intent_lower for kw in ("风险", "挑战", "问题", "限制", "缺点", "危险", "risk")):
        parts.append("检索需求：需要风险分析、挑战或负面案例")
    elif any(kw in intent_lower for kw in ("方案", "架构", "设计", "流程", "路径", "方法", "solution")):
        parts.append("检索需求：需要方案设计、架构说明或实施路径")

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
    *,
    tavily_enabled: bool | None = None,
    slide_cache: dict[str, list[dict]] | None = None,
    force_refresh: bool = False,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Retrieve evidence for all pages; reuse slide_cache when skeleton slice keys match."""
    use_tavily = settings.retrieval_tavily_enabled if tavily_enabled is None else tavily_enabled
    cache: dict[str, list[dict]] = dict(slide_cache or {})
    by_slide: dict[str, list[dict]] = {}
    slides_to_fetch: list[dict] = []

    for slide in skeleton:
        slide_id = str(slide.get("slide_id") or "")
        cache_key = _retrieval_cache_key(slide, retrieval_depth, use_tavily)
        if not force_refresh and cache_key in cache:
            by_slide[slide_id] = [dict(hit) for hit in cache[cache_key]]
        else:
            slides_to_fetch.append(slide)

    if slides_to_fetch:
        fetched = _retrieve_for_pages_uncached(
            topic,
            retrieval_depth,
            slides_to_fetch,
            clarification,
            tavily_enabled=use_tavily,
        )
        for slide in slides_to_fetch:
            slide_id = str(slide.get("slide_id") or "")
            hits = fetched.get(slide_id, [])
            by_slide[slide_id] = hits
            cache_key = _retrieval_cache_key(slide, retrieval_depth, use_tavily)
            cache[cache_key] = _strip_evidence_ids(hits)

    return by_slide, cache


def _retrieve_for_pages_uncached(
    topic: str,
    retrieval_depth: str,
    skeleton: list[dict],
    clarification: dict | None,
    *,
    tavily_enabled: bool,
) -> dict[str, list[dict]]:
    """Retrieve evidence for pages without reading the per-task cache."""
    retriever = get_retriever(
        documents_dir=settings.retrieval_documents_dir,
        chroma_persist_dir=settings.retrieval_chroma_dir,
        tavily_api_key=(settings.tavily_api_key or "") if tavily_enabled else "",
    )
    clarification_text = _clarification_text(clarification)
    depth = RetrievalDepth(retrieval_depth)
    tavily_max = settings.retrieval_tavily_max_pages if tavily_enabled else 0
    tavily_used = 0

    by_slide: dict[str, list[dict]] = {}

    async def _run() -> None:
        nonlocal tavily_used
        semaphore = asyncio.Semaphore(max(1, settings.retrieval_parallel_pages))
        tavily_lock = asyncio.Lock()

        async def _retrieve_one(slide: dict) -> tuple[str, list[dict]]:
            nonlocal tavily_used
            slide_id = str(slide.get("slide_id") or "")
            try:
                query = _build_page_query(topic, slide, clarification_text)
                async with tavily_lock:
                    use_web = bool(settings.tavily_api_key) and (
                        tavily_enabled and (tavily_max == 0 or tavily_used < tavily_max)
                    )
                    if use_web and tavily_max > 0:
                        tavily_used += 1
                local_depth = depth if use_web else RetrievalDepth("L0")
                result = await retriever.retrieve(RetrievalRequest(query=query, depth=local_depth))
                # R3: 来源质量分级过滤——优先高质量来源，降权聚合/营销页
                selected: list[dict] = []
                deprioritized: list[dict] = []
                for hit in result.hits:
                    hit_dict = hit.model_dump()
                    source = str(hit_dict.get("source_id") or "").lower()
                    if _is_low_quality_source(source):
                        deprioritized.append(hit_dict)
                    else:
                        selected.append(hit_dict)
                    if len(selected) >= 3:
                        break
                # 若高质量来源不足 2 条，用降权来源补充
                if len(selected) < 2:
                    for hit_dict in deprioritized:
                        selected.append(hit_dict)
                        if len(selected) >= 3:
                            break
                return slide_id, selected[:3]
            except Exception as exc:
                raise _classify_retrieval_exception(exc, slide_id) from exc

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

    return f"""你是PPT大纲助手。根据以下信息为指定页面生成完整的页面内容。

## 演示主题
{topic}

## 本页信息
- 页面标题：{slide_title}
- 页面意图：{intent or "无"}
- 用户补充要求：{user_notes or "无"}

## 参考资料（仅供撰写内容时参考，勿在输出中填写证据编号）
{evidence_block}

## 输出要求
只输出一个JSON对象：
{{
  "key_message": "本页核心结论（1～2 句，约 20～40 字，说清楚「这页要证明什么」）",
  "bullets": [
    {{"bullet_id": "{slide_id}-b1", "text": "要点：含关键信息、依据或例子，单条约 40～80 字"}}
  ],
  "speaker_notes": "讲者备注：4～6 句可讲述话术，含本页展开顺序与过渡到下页",
  "visual_suggestion": "建议配图或图表类型（如：柱状图对比、流程图、示意图），若无必要可填null",
  "takeaway": "页级小结：1～2 句行动建议或启示（背景页可填 null）"
}}

硬性要求：
1) bullets 至少 2 个，最多 6 个；每条 bullet 只含 bullet_id 与 text，不要填写证据编号字段；
2) 每条 bullet 的 text 必须具体、可讲，避免「加强XX」「提升YY」等空话；有参考资料时融入事实、数据或案例表述；
3) key_message 必须输出非空字符串，与 bullets 内容一致、可独立读懂；
4) 要点内容若来自参考资料，在 text 中自然表述即可；证据引用由系统在生成后自动绑定；
5) 不要输出 Markdown，不要输出解释文字，只输出 JSON。"""


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
    slide_id = str(slide.get("slide_id") or "")
    try:
        if not settings.use_real_llm:
            return _stub_page(slide)
        if not settings.openai_api_key:
            raise SlideWorkflowError(
                "LLM_ERROR",
                "未配置 OPENAI_API_KEY，无法调用模型。",
                slide_id=slide_id,
                phase="llm_page",
                retryable=False,
            )
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

        bullets_in = raw.get("bullets", []) if isinstance(raw.get("bullets", []), list) else []
        bullets: list[dict] = []
        for jdx, bullet in enumerate(bullets_in[:6], start=1):
            if not isinstance(bullet, dict):
                continue
            bullets.append({
                "bullet_id": str(bullet.get("bullet_id") or f"{slide_id}-b{jdx}"),
                "text": str(bullet.get("text") or "待补充要点"),
                "evidence_ids": [],
            })
        if len(bullets) < 2:
            bullets.append({"bullet_id": f"{slide_id}-b{len(bullets)+1}", "text": "待补充要点", "evidence_ids": []})

        # B1: 解析并规范化新增字段，缺失时补默认值
        key_message_raw = raw.get("key_message")
        key_message = str(key_message_raw).strip() if key_message_raw and str(key_message_raw).strip() else str(slide.get("title") or slide_id)

        visual_suggestion_raw = raw.get("visual_suggestion")
        visual_suggestion: str | None = None
        if visual_suggestion_raw and str(visual_suggestion_raw).strip().lower() not in ("null", "none", ""):
            visual_suggestion = str(visual_suggestion_raw).strip()

        takeaway_raw = raw.get("takeaway")
        takeaway: str | None = None
        if takeaway_raw and str(takeaway_raw).strip().lower() not in ("null", "none", ""):
            takeaway = str(takeaway_raw).strip()

        return {
            "slide_id": slide_id,
            "title": str(slide.get("title") or slide_id),
            "key_message": key_message,
            "bullets": bullets,
            "speaker_notes": str(raw.get("speaker_notes") or ""),
            "visual_suggestion": visual_suggestion,
            "takeaway": takeaway,
        }
    except SlideWorkflowError:
        raise
    except Exception as exc:
        raise _classify_llm_exception(exc, slide_id) from exc


def _stub_page(slide: dict) -> dict:
    slide_id = str(slide.get("slide_id") or "")
    return {
        "slide_id": slide_id,
        "title": str(slide.get("title") or slide_id),
        "key_message": str(slide.get("title") or slide_id),  # B1: 默认用标题作占位
        "bullets": [
            {"bullet_id": f"{slide_id}-b1", "text": "待补充要点", "evidence_ids": []},
            {"bullet_id": f"{slide_id}-b2", "text": "待补充要点", "evidence_ids": []},
        ],
        "speaker_notes": "",
        "visual_suggestion": None,  # B1: 可选字段，默认空
        "takeaway": None,           # B1: 可选字段，默认空
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
    runtime = task.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    retrieval_depth = str(runtime.get("generation_retrieval_depth") or input_data.get("retrieval_depth", "L1"))
    tavily_enabled = runtime.get("generation_tavily_enabled")
    if tavily_enabled is not None:
        use_tavily = bool(tavily_enabled)
    else:
        use_tavily = settings.retrieval_tavily_enabled
    force_refresh = bool(runtime.get("force_refresh_retrieval"))
    slide_cache = runtime.get("retrieval_cache")
    if not isinstance(slide_cache, dict):
        slide_cache = {}
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
    retrieval_by_slide, slide_cache = retrieve_for_pages(
        topic,
        retrieval_depth,
        skeleton,
        clarification,
        tavily_enabled=use_tavily,
        slide_cache=slide_cache,
        force_refresh=force_refresh,
    )
    runtime["retrieval_cache"] = slide_cache
    task["runtime"] = runtime
    if on_progress:
        on_progress(task)

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
            except SlideWorkflowError as exc:
                logger.exception("Page generation failed for slide=%s", slide_id)
                page = _stub_page(slide)
                page["generation_status"] = "failed"
                page["error"] = {
                    "code": exc.code,
                    "message": exc.message,
                }
                page_results[slide_id] = page
                failed_pages += 1
            except Exception as exc:
                logger.exception("Page generation failed for slide=%s", slide_id)
                page = _stub_page(slide)
                page["generation_status"] = "failed"
                page["error"] = {
                    "code": "INTERNAL_ERROR",
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
