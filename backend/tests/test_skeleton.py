from __future__ import annotations

import json
from typing import Any

from app.services import skeleton


def _task(page_answer: str = "5 页") -> dict[str, Any]:
    return {
        "input": {
            "topic": "生成式 AI 教学应用",
            "audience": "课程答辩",
            "duration_minutes": 15,
            "source_type": "short_topic",
            "raw_notes": "强调实现路径和风险边界",
        },
        "clarification": {
            "submitted": True,
            "questions": [
                {"question_id": "goal", "prompt": "核心结论？", "answer": "AI 可以提升备课效率"},
                {"question_id": "page_range", "prompt": "期望页数？", "answer": page_answer},
            ],
        },
    }


def test_generate_skeleton_uses_llm_when_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, Any] = {}

    class _Message:
        content = json.dumps(
            {
                "chapters": [
                    {"chapter_id": "ch1", "title": "核心机会", "slide_ids": ["s1", "s2"]},
                    {"chapter_id": "ch2", "title": "落地路径", "slide_ids": ["s3", "s4", "s5"]},
                ],
                "slides": [
                    {"slide_id": "custom", "title": "AI 教学的核心机会", "intent": "说明机会", "user_notes": "强调课堂"},
                    {"slide_id": "bad-id", "title": "落地路径", "intent": "说明路径", "user_notes": ""},
                ]
            },
            ensure_ascii=False,
        )

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **payload):  # type: ignore[no-untyped-def]
            captured.update(payload)
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(skeleton.settings, "use_real_llm", True)
    monkeypatch.setattr(skeleton.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(skeleton.settings, "openai_base_url", None)
    monkeypatch.setattr(skeleton, "OpenAI", lambda **_: _Client())

    result = skeleton.generate_outline_skeleton(_task("5 页"))
    slides = result["slides"]
    chapters = result["chapters"]

    assert captured["model"] == skeleton.settings.llm_model
    assert "response_format" in captured
    assert len(slides) == 5
    assert [slide["slide_id"] for slide in slides] == ["s1", "s2", "s3", "s4", "s5"]
    assert slides[0]["title"] == "AI 教学的核心机会"
    assert slides[0]["user_notes"] == "强调课堂"
    assert "bullets" not in slides[0]
    assert slides[2]["title"]

    assert len(chapters) >= 2
    assert chapters[0]["chapter_id"] == "ch1"
    assert chapters[0]["slide_ids"] == ["s1", "s2"]
    assert chapters[1]["chapter_id"] == "ch2"
    assert chapters[1]["slide_ids"] == ["s3", "s4", "s5"]


def test_generate_skeleton_falls_back_without_api_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(skeleton.settings, "use_real_llm", True)
    monkeypatch.setattr(skeleton.settings, "openai_api_key", None)

    result = skeleton.generate_outline_skeleton(_task("6 页"))
    slides = result["slides"]
    chapters = result["chapters"]

    assert len(slides) == 6
    assert slides[0]["slide_id"] == "s1"
    assert "生成式 AI 教学应用" in slides[0]["title"]

    assert len(chapters) >= 2
    assert all(len(ch.get("slide_ids", [])) > 0 for ch in chapters)
    all_ch_slide_ids = [sid for ch in chapters for sid in ch.get("slide_ids", [])]
    assert set(all_ch_slide_ids) == {s["slide_id"] for s in slides}
