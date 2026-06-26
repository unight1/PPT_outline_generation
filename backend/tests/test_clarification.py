from __future__ import annotations

from types import SimpleNamespace

from app.services.clarification import (
    _extract_json_object,
    _slugify_question_id,
    build_fallback_clarification_questions,
    estimate_page_range,
)


def _payload(**kw):
    defaults = dict(topic="AI教育", duration_minutes=15, audience=None, raw_notes=None,
                    source_type="short_topic", document_title=None, document_text=None,
                    retrieval_depth="L1", language="zh")
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ── Pure functions ──────────────────────────────────────────


def test_estimate_page_range():
    assert estimate_page_range(10) == "5-10 页"
    assert estimate_page_range(30) == "15-30 页"
    assert estimate_page_range(6) == "5-7 页"


def test_slugify_question_id():
    assert _slugify_question_id("Hello World 测试") == "hello_world"
    assert _slugify_question_id("  A B  C  ") == "a_b_c"
    assert _slugify_question_id("") == ""


def test_extract_json_object_valid():
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_fenced():
    result = _extract_json_object('```json\n{"a":1}\n```')
    assert result == {"a": 1}


def test_extract_json_object_inline():
    result = _extract_json_object('text {"x": 2} more')
    assert result == {"x": 2}


def test_extract_json_object_invalid_raises():
    try:
        _extract_json_object("not json")
        assert False, "should have raised"
    except RuntimeError:
        pass


# ── Fallback questions ──────────────────────────────────────


def test_build_fallback_includes_topic():
    qs = build_fallback_clarification_questions(_payload())
    assert any("AI教育" in q["prompt"] for q in qs)
    assert all("question_id" in q and "prompt" in q for q in qs)
    for q in qs:
        for key in ("options", "type", "choices", "input_type"):
            assert key not in q


def test_build_fallback_has_expected_questions():
    qs = build_fallback_clarification_questions(_payload())
    ids = {q["question_id"] for q in qs}
    assert "goal" in ids
    assert "style" in ids
    assert "depth" in ids
    assert "page_range" in ids


def test_build_fallback_context_omits_audience_when_filled():
    qs = build_fallback_clarification_questions(_payload(audience="本科课堂"))
    ids = {q["question_id"] for q in qs}
    assert "audience_level" not in ids


# ── LLM path ────────────────────────────────────────────────


def test_build_clarification_with_llm(monkeypatch):
    from app.services import clarification

    class FakeResponse:
        class Choice:
            message = SimpleNamespace(content='{"questions":[{"question_id":"q1","prompt":"What?","answer":null}]}')
        choices = [Choice()]

    monkeypatch.setattr(clarification, "OpenAI", lambda **kw: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: FakeResponse()))
    ))
    monkeypatch.setattr(clarification.settings, "use_real_llm", True)
    monkeypatch.setattr(clarification.settings, "openai_api_key", "fake-key")
    monkeypatch.setattr(clarification.settings, "llm_model", "test-model")
    monkeypatch.setattr(clarification.settings, "openai_base_url", None)

    questions = clarification.build_clarification_questions(_payload())
    assert len(questions) >= 1
    assert questions[0]["question_id"] == "q1"


def test_build_clarification_falls_back_without_llm(monkeypatch):
    from app.services import clarification
    monkeypatch.setattr(clarification.settings, "use_real_llm", False)
    questions = clarification.build_clarification_questions(_payload())
    assert len(questions) >= 3
    assert all(isinstance(q["question_id"], str) for q in questions)


def test_build_clarification_falls_back_on_llm_error(monkeypatch):
    from app.services import clarification
    monkeypatch.setattr(clarification.settings, "use_real_llm", True)
    monkeypatch.setattr(clarification.settings, "openai_api_key", "fake-key")
    monkeypatch.setattr(clarification, "OpenAI", lambda **kw: (_ for _ in ()).throw(RuntimeError("LLM down")))
    questions = clarification.build_clarification_questions(_payload())
    assert len(questions) >= 3


# ── Normalize ───────────────────────────────────────────────


def _fallback():
    return build_fallback_clarification_questions(_payload())


def test_normalize_filters_forbidden_keys():
    from app.services.clarification import _normalize_questions
    raw = [
        {"question_id": "q1", "prompt": "P1"},
        {"question_id": "q2", "prompt": "P2", "options": ["a", "b"]},
    ]
    normalized = _normalize_questions(raw, fallback=_fallback())
    assert len(normalized) >= 2
    assert normalized[0]["question_id"] == "q1"
    for q in normalized:
        assert "options" not in q


def test_normalize_pads_from_fallback():
    from app.services.clarification import _normalize_questions
    raw = [{"question_id": "q1", "prompt": "Only one"}]
    normalized = _normalize_questions(raw, fallback=_fallback())
    assert len(normalized) >= 3


def test_normalize_handles_empty_input():
    from app.services.clarification import _normalize_questions
    normalized = _normalize_questions([], fallback=_fallback())
    assert len(normalized) >= 3


def test_normalize_caps_at_five():
    from app.services.clarification import _normalize_questions
    fallback = _fallback()
    raw = [
        {"question_id": "q1", "prompt": "A"},
        {"question_id": "q2", "prompt": "B"},
        {"question_id": "q3", "prompt": "C"},
        {"question_id": "q4", "prompt": "D"},
        {"question_id": "q5", "prompt": "E"},
        {"question_id": "q6", "prompt": "F"},
    ]
    normalized = _normalize_questions(raw, fallback=fallback)
    assert len(normalized) <= 5
