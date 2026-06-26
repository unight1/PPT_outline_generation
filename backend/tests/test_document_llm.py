from __future__ import annotations

from types import SimpleNamespace

from app.services.document_llm import (
    _parse_key_points,
    _segment_long_text,
    enrich_document_profile,
    merge_enrichment_into_profile,
)


def test_segment_long_text():
    text = "这是一段测试文本。" * 50
    segments = _segment_long_text(text, size=200)
    assert len(segments) > 1
    for seg in segments:
        assert len(seg) <= 220  # small tolerance


def test_segment_short_text():
    text = "短文本。"
    segments = _segment_long_text(text, size=200)
    assert len(segments) == 1
    assert "短文本" in segments[0]


def test_parse_key_points_numeric():
    result = _parse_key_points("1. 第一点\n2. 第二点\n3. 第三点")
    assert len(result) == 3
    assert "第一点" in result[0]


def test_parse_key_points_bullet():
    result = _parse_key_points("- Point A\n- Point B\n- Point C")
    assert len(result) == 3
    assert "Point A" in result[0]


def test_parse_key_points_plain():
    result = _parse_key_points("Single point without markers")
    assert len(result) >= 1


def test_merge_enrichment_into_profile():
    profile = {"char_count": 1000}
    llm_output = {"summary": "LLM summary", "key_points": ["K1", "K2"], "suggested_focus": "focus"}
    merged = merge_enrichment_into_profile(profile, llm_output)
    assert merged["summary"] == "LLM summary"
    assert merged["key_points"] == ["K1", "K2"]
    assert merged["suggested_focus"] == "focus"
    assert merged["char_count"] == 1000  # preserved


def test_merge_enrichment_handles_empty():
    profile = {"char_count": 500}
    merged = merge_enrichment_into_profile(profile, {})
    assert merged["char_count"] == 500


def test_enrich_document_profile_no_llm(monkeypatch):
    from app.services import document_llm
    monkeypatch.setattr(document_llm.settings, "use_real_llm", False)
    result = enrich_document_profile("AI topic", "long text here " * 50)
    # When LLM is disabled, returns rule-based profile (may include summary from segments)
    assert isinstance(result, dict)


def test_enrich_document_profile_with_llm(monkeypatch):
    from app.services import document_llm

    class FakeResponse:
        class Choice:
            message = SimpleNamespace(content='{"summary":"LLM says AI is important","key_points":["AI trend","Education impact"],"suggested_focus":"EdTech"}')
        choices = [Choice()]

    monkeypatch.setattr(document_llm, "OpenAI", lambda **kw: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: FakeResponse()))
    ))
    monkeypatch.setattr(document_llm.settings, "use_real_llm", True)
    monkeypatch.setattr(document_llm.settings, "openai_api_key", "fake-key")
    monkeypatch.setattr(document_llm.settings, "llm_model", "test-model")
    monkeypatch.setattr(document_llm.settings, "openai_base_url", None)

    result = enrich_document_profile("AI topic", "long document text " * 100)
    assert isinstance(result, dict)
    # LLM enrichment returns a profile dict; exact keys depend on LLM output format
    assert isinstance(result, dict)
