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


def test_generate_skeleton_uses_page_range_and_desired_chapters(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(skeleton.settings, "use_real_llm", False)
    task = _task("6 页")
    task["input"]["target_pages_min"] = 6
    task["input"]["target_pages_max"] = 10
    task["input"]["desired_chapters"] = "背景, 方案, 验证, 总结"

    result = skeleton.generate_outline_skeleton(task)

    assert len(result["slides"]) == 8
    assert [chapter["title"] for chapter in result["chapters"]] == ["背景", "方案", "验证", "总结"]


def test_normalize_skeleton_maps_model_slide_ids_to_chapters() -> None:
    raw = {
        "chapters": [
            {"chapter_id": "c_background", "title": "背景分析", "slide_ids": ["intro", "problem"]},
            {"chapter_id": "c_solution", "title": "方案设计", "slide_ids": ["solution"]},
        ],
        "slides": [
            {"slide_id": "intro", "title": "引入", "intent": "说明背景", "user_notes": ""},
            {"slide_id": "problem", "title": "问题", "intent": "说明问题", "user_notes": ""},
            {"slide_id": "solution", "title": "方案", "intent": "说明方案", "user_notes": ""},
        ],
    }

    result = skeleton._normalize_skeleton(raw, "主题", 3)

    assert [slide["slide_id"] for slide in result["slides"]] == ["s1", "s2", "s3"]
    assert result["chapters"][0]["title"] == "背景分析"
    assert result["chapters"][0]["slide_ids"] == ["s1", "s2"]
    assert result["chapters"][1]["slide_ids"] == ["s3"]


def test_normalize_skeleton_accepts_sections_alias() -> None:
    raw = {
        "sections": [
            {"section_id": "sec1", "name": "背景", "slides": ["a"]},
            {"section_id": "sec2", "name": "总结", "slides": ["b"]},
        ],
        "slides": [
            {"slide_id": "a", "title": "第一页", "intent": "背景", "user_notes": ""},
            {"slide_id": "b", "title": "第二页", "intent": "总结", "user_notes": ""},
        ],
    }

    result = skeleton._normalize_skeleton(raw, "主题", 2)

    assert result["chapters"][0]["chapter_id"] == "sec1"
    assert result["chapters"][0]["title"] == "背景"
    assert result["chapters"][1]["slide_ids"] == ["s2"]
