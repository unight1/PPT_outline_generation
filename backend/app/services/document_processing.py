from __future__ import annotations

import re
from collections import Counter
from typing import Any

_SENTENCE_END = ("。", "！", "？", ".", "!", "?")
_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}")


def _first_sentence(text: str, max_len: int = 160) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    for sep in _SENTENCE_END:
        if sep in stripped:
            candidate = stripped.split(sep, 1)[0].strip()
            if len(candidate) >= 8:
                return (candidate + sep)[:max_len]
    return stripped[:max_len]


def _extract_keywords(normalized: str, limit: int = 12) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(normalized.lower())
    if not tokens:
        return []
    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "可以",
        "进行",
        "通过",
        "以及",
        "我们",
        "他们",
        "一个",
        "需要",
        "如果",
        "因为",
        "所以",
        "但是",
        "已经",
        "没有",
        "作为",
        "其中",
        "主要",
        "相关",
        "内容",
        "问题",
        "方案",
        "系统",
    }
    filtered = [token for token in tokens if token not in stop]
    ranked = Counter(filtered).most_common(limit * 2)
    keywords: list[str] = []
    for word, _ in ranked:
        if word in keywords:
            continue
        keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords


def build_document_profile(document_text: str | None) -> dict[str, Any] | None:
    """Split, summarize, and extract lightweight signals from long-document input."""
    text = (document_text or "").strip()
    if not text:
        return None

    normalized = " ".join(text.split())
    segments: list[str] = []
    chunk_size = 500
    max_chars = 8000
    for start in range(0, min(len(normalized), max_chars), chunk_size):
        end = min(start + chunk_size, len(normalized))
        part = normalized[start:end].strip()
        if part:
            segments.append(part)

    key_points = [_first_sentence(segment) for segment in segments[:8] if segment.strip()]
    keywords = _extract_keywords(normalized[:6000])

    return {
        "char_count": len(normalized),
        "segment_count": len(segments),
        "summary": normalized[:1500],
        "segments": segments[:12],
        "key_points": key_points,
        "keywords": keywords,
    }
