from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import tasks as tasks_route
from app.services.page_generation import (
    _build_page_prompt,
    _build_page_query,
    _clarification_text,
    merge_pages_to_outline,
)


def setup_function() -> None:
    tasks_route.TASK_STORE.clear()
    tasks_route.USE_DB_STORE = False


# ── merge_pages_to_outline ──────────────────────────────────


def test_merge_pages_to_outline_basic() -> None:
    skeleton = [
        {"slide_id": "s1", "title": "背景", "intent": "", "user_notes": ""},
        {"slide_id": "s2", "title": "方案", "intent": "", "user_notes": ""},
    ]
    page_results = {
        "s1": {
            "slide_id": "s1", "title": "背景",
            "bullets": [{"bullet_id": "s1-b1", "text": "要点A", "evidence_ids": ["ev_1"]}],
            "speaker_notes": "备注A",
        },
        "s2": {
            "slide_id": "s2", "title": "方案",
            "bullets": [{"bullet_id": "s2-b1", "text": "要点B", "evidence_ids": ["ev_2"]}],
            "speaker_notes": "",
        },
    }
    retrieval = {
        "s1": [{"evidence_id": "ev_1", "snippet": "证据1", "source_id": "paper.pdf", "locator": "L1-L5", "score": 0.9, "confidence": 0.8}],
        "s2": [{"evidence_id": "ev_2", "snippet": "证据2", "source_id": "https://example.com", "locator": "Web Title", "score": 0.75, "confidence": None}],
    }

    outline = merge_pages_to_outline("AI教育", skeleton, page_results, retrieval, "L1")

    assert outline["title"] == "AI教育"
    assert len(outline["slides"]) == 2
    assert outline["slides"][0]["speaker_notes"] == "备注A"
    assert outline["slides"][1]["speaker_notes"] == ""

    assert len(outline["evidence_catalog"]) == 2
    assert outline["evidence_catalog"][0]["evidence_id"] == "ev_1"
    assert outline["evidence_catalog"][1]["source_id"] == "https://example.com"

    assert len(outline["page_evidence_map"]) == 2
    assert outline["page_evidence_map"][0]["slide_title"] == "背景"
    assert outline["page_evidence_map"][0]["evidence_trace"][0]["bullet_ids"] == ["s1-b1"]

    assert outline["meta"]["retrieval_depth"] == "L1"
    assert outline["meta"]["evidence_coverage_total"] >= 1
    assert "schema_version" in outline["meta"]


def test_merge_pages_empty_skeleton() -> None:
    outline = merge_pages_to_outline("测试", [], {}, {}, "L0")
    assert outline["slides"] == []
    assert outline["evidence_catalog"] == []
    assert outline["page_evidence_map"] == []


def test_merge_pages_stub_for_missing_page() -> None:
    skeleton = [{"slide_id": "s1", "title": "某页", "intent": "", "user_notes": ""}]
    page_results = {}  # s1 not found → stub
    retrieval = {}

    outline = merge_pages_to_outline("测试", skeleton, page_results, retrieval, "L0")
    assert len(outline["slides"]) == 1
    slide = outline["slides"][0]
    assert slide["slide_id"] == "s1"
    assert len(slide["bullets"]) >= 2
    assert slide["bullets"][0]["text"] == "待补充要点"


def test_merge_pages_preserves_bullet_order() -> None:
    skeleton = [{"slide_id": "s1", "title": "页", "intent": "", "user_notes": ""}]
    page_results = {
        "s1": {
            "slide_id": "s1", "title": "页",
            "bullets": [
                {"bullet_id": "s1-b3", "text": "第三", "evidence_ids": []},
                {"bullet_id": "s1-b1", "text": "第一", "evidence_ids": ["ev_1"]},
                {"bullet_id": "s1-b2", "text": "第二", "evidence_ids": []},
            ],
            "speaker_notes": "",
        }
    }
    retrieval = {"s1": [{"evidence_id": "ev_1", "snippet": "x", "source_id": "s", "locator": "L1", "score": 0.5, "confidence": 0.5}]}
    outline = merge_pages_to_outline("t", skeleton, page_results, retrieval, "L1")
    slide = outline["slides"][0]
    assert [b["bullet_id"] for b in slide["bullets"]] == ["s1-b3", "s1-b1", "s1-b2"]


def test_merge_pages_shared_evidence_across_bullets() -> None:
    skeleton = [{"slide_id": "s1", "title": "页", "intent": "", "user_notes": ""}]
    page_results = {
        "s1": {
            "slide_id": "s1", "title": "页",
            "bullets": [
                {"bullet_id": "s1-b1", "text": "A", "evidence_ids": ["ev_1"]},
                {"bullet_id": "s1-b2", "text": "B", "evidence_ids": ["ev_1"]},
            ],
            "speaker_notes": "",
        }
    }
    retrieval = {"s1": [{"evidence_id": "ev_1", "snippet": "共用的证据", "source_id": "s", "locator": "L1", "score": 0.5, "confidence": 0.5}]}
    outline = merge_pages_to_outline("t", skeleton, page_results, retrieval, "L1")
    trace = outline["page_evidence_map"][0]["evidence_trace"]
    assert len(trace) == 1
    assert set(trace[0]["bullet_ids"]) == {"s1-b1", "s1-b2"}


# ── _build_page_query ───────────────────────────────────────


def test_build_page_query_basic() -> None:
    slide = {"slide_id": "s1", "title": "背景"}
    query = _build_page_query("AI教育", slide, "")
    assert "AI教育" in query
    assert "背景" in query


def test_build_page_query_with_intent_and_notes() -> None:
    slide = {"slide_id": "s2", "title": "方案", "intent": "介绍技术架构", "user_notes": "要有对比图"}
    query = _build_page_query("AI教育", slide, "需要学术引用")
    assert "方案" in query
    assert "介绍技术架构" in query
    assert "要有对比图" in query
    assert "补充约束" in query
    assert "需要学术引用" in query


def test_build_page_query_skips_empty_fields() -> None:
    slide = {"slide_id": "s3"}
    query = _build_page_query("主题", slide, "")
    assert "页面目标" not in query
    assert "本页意图" not in query


# ── _build_page_prompt ──────────────────────────────────────


def test_build_page_prompt_includes_evidence() -> None:
    slide = {"slide_id": "s1", "title": "背景", "intent": "", "user_notes": ""}
    evidence = [
        {"evidence_id": "ev_1", "snippet": "AI改变教育模式", "source_id": "paper.pdf", "locator": "L10"},
        {"evidence_id": "ev_2", "snippet": "ML应用广泛", "source_id": "https://example.com", "locator": "Web"},
    ]
    prompt = _build_page_prompt("AI教育", slide, evidence)
    assert "ev_1" in prompt
    assert "AI改变教育模式" in prompt
    assert "paper.pdf" in prompt
    assert "ev_2" in prompt
    assert "https://example.com" in prompt
    assert "s1-b1" in prompt  # bullet_id template


def test_build_page_prompt_no_evidence() -> None:
    slide = {"slide_id": "s2", "title": "方案", "intent": "技术架构", "user_notes": "要详细"}
    prompt = _build_page_prompt("AI教育", slide, [])
    assert "（无参考资料）" in prompt
    assert "技术架构" in prompt
    assert "要详细" in prompt


def test_build_page_prompt_intent_and_notes_included() -> None:
    slide = {"slide_id": "s1", "title": "概述", "intent": "介绍背景", "user_notes": "加入案例"}
    prompt = _build_page_prompt("主题", slide, [])
    assert "介绍背景" in prompt
    assert "加入案例" in prompt


# ── _clarification_text ─────────────────────────────────────


def test_clarification_text_basic() -> None:
    c = {
        "questions": [
            {"question_id": "q1", "prompt": "核心结论？", "answer": "AI提升效率"},
            {"question_id": "q2", "prompt": "风格？", "answer": "正式汇报"},
        ],
        "submitted": True,
    }
    text = _clarification_text(c)
    assert "核心结论？：AI提升效率" in text
    assert "风格？：正式汇报" in text


def test_clarification_text_empty() -> None:
    assert _clarification_text(None) == ""
    assert _clarification_text({}) == ""


def test_clarification_text_skips_missing_answers() -> None:
    c = {
        "questions": [
            {"question_id": "q1", "prompt": "A?", "answer": ""},
            {"question_id": "q2", "prompt": "B?", "answer": "有答案"},
        ]
    }
    text = _clarification_text(c)
    assert "A?" not in text
    assert "B?：有答案" in text


# ── API: slides/generate ───────────────────────────────────


def _make_task_in_memory(topic="AI教育", retrieval_depth="L1", **overrides) -> str:
    from uuid import uuid4
    from datetime import datetime, timezone

    task_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    task = {
        "task_id": task_id,
        "schema_version": "v1.0.0",
        "status": "clarifying",
        "created_at": now,
        "updated_at": now,
        "input": {"topic": topic, "retrieval_depth": retrieval_depth},
        "clarification": {"questions": [], "submitted": False},
        "outline": None,
        "outline_skeleton": None,
        "progress": {"phase": "idle", "current": None, "total": None, "message": "", "percent": None},
        "error": None,
        "runtime": {"generation_attempts": 0, "last_started_at": None, "last_finished_at": None},
    }
    task.update(overrides)
    tasks_route.TASK_STORE[task_id] = task
    return task_id


def test_slides_generate_requires_skeleton() -> None:
    task_id = _make_task_in_memory(status="pending", clarification_submitted=True)
    tasks_route.TASK_STORE[task_id]["clarification"]["submitted"] = True

    client = TestClient(app)
    resp = client.post(f"/api/tasks/{task_id}/slides/generate", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"


def test_slides_generate_requires_pending() -> None:
    task_id = _make_task_in_memory(
        status="done",
        outline_skeleton=[{"slide_id": "s1", "title": "页1", "intent": "", "user_notes": ""}],
        clarification={"questions": [], "submitted": True},
    )
    client = TestClient(app)
    resp = client.post(f"/api/tasks/{task_id}/slides/generate", json={})
    assert resp.status_code == 409


def test_slides_generate_requires_submitted_clarification() -> None:
    task_id = _make_task_in_memory(
        status="pending",
        outline_skeleton=[{"slide_id": "s1", "title": "页1", "intent": "", "user_notes": ""}],
    )
    # clarification.submitted is False by default
    client = TestClient(app)
    resp = client.post(f"/api/tasks/{task_id}/slides/generate", json={})
    assert resp.status_code == 409


def test_slides_generate_accepted_with_valid_state() -> None:
    task_id = _make_task_in_memory(
        status="pending",
        outline_skeleton=[{"slide_id": "s1", "title": "页1", "intent": "", "user_notes": ""}],
        clarification={"questions": [], "submitted": True},
    )
    # Mock the background executor to avoid real page generation
    old_enqueue = tasks_route.enqueue_slides_generation
    tasks_route.enqueue_slides_generation = lambda tid, c: None  # type: ignore[assignment]
    try:
        client = TestClient(app)
        resp = client.post(f"/api/tasks/{task_id}/slides/generate", json={"concurrency": 2})
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True
        assert resp.json()["status"] == "generating"
    finally:
        tasks_route.enqueue_slides_generation = old_enqueue


def test_slides_generate_respects_concurrency_param() -> None:
    task_id = _make_task_in_memory(
        status="pending",
        outline_skeleton=[{"slide_id": "s1", "title": "页1", "intent": "", "user_notes": ""}],
        clarification={"questions": [], "submitted": True},
    )
    captured_concurrency = []
    old_enqueue = tasks_route.enqueue_slides_generation
    tasks_route.enqueue_slides_generation = lambda tid, c: captured_concurrency.append(c)  # type: ignore[assignment]
    try:
        client = TestClient(app)
        client.post(f"/api/tasks/{task_id}/slides/generate", json={"concurrency": 3})
        assert captured_concurrency == [3]
    finally:
        tasks_route.enqueue_slides_generation = old_enqueue


# ── API: slides/{id}/regenerate ─────────────────────────────


def test_regenerate_requires_outline() -> None:
    task_id = _make_task_in_memory(status="done")
    client = TestClient(app)
    resp = client.post(f"/api/tasks/{task_id}/slides/s1/regenerate", json={})
    assert resp.status_code == 409


def test_regenerate_slide_not_found() -> None:
    task_id = _make_task_in_memory(
        status="done",
        outline={
            "title": "测试",
            "slides": [{"slide_id": "s1", "title": "页1", "bullets": [], "speaker_notes": ""}],
            "evidence_catalog": [],
            "meta": {},
        },
    )
    client = TestClient(app)
    resp = client.post(f"/api/tasks/{task_id}/slides/s_not_exist/regenerate", json={})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SLIDE_NOT_FOUND"


def test_regenerate_requires_done_or_pending() -> None:
    task_id = _make_task_in_memory(
        status="failed",
        outline={
            "title": "测试",
            "slides": [{"slide_id": "s1", "title": "页1", "bullets": [], "speaker_notes": ""}],
            "evidence_catalog": [],
            "meta": {},
        },
        error={"code": "INTERNAL_ERROR", "message": "x", "details": {}},
    )
    client = TestClient(app)
    resp = client.post(f"/api/tasks/{task_id}/slides/s1/regenerate", json={})
    assert resp.status_code == 409


def test_regenerate_accepted() -> None:
    task_id = _make_task_in_memory(
        status="done",
        outline={
            "title": "测试",
            "slides": [{"slide_id": "s1", "title": "页1", "bullets": [], "speaker_notes": ""}],
            "evidence_catalog": [],
            "meta": {},
        },
    )
    old_enqueue = tasks_route.enqueue_regenerate_slide
    tasks_route.enqueue_regenerate_slide = lambda tid, sid, ui: None  # type: ignore[assignment]
    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/tasks/{task_id}/slides/s1/regenerate",
            json={"user_instruction": "加入更多数据"},
        )
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True
        assert resp.json()["slide_id"] == "s1"
    finally:
        tasks_route.enqueue_regenerate_slide = old_enqueue


# ── task_snapshot v1 fields ─────────────────────────────────


def test_task_snapshot_includes_v1_fields() -> None:
    task_id = _make_task_in_memory()
    client = TestClient(app)
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    task = resp.json()
    assert "outline_skeleton" in task
    assert "progress" in task
    assert task["progress"]["phase"] == "idle"


def test_create_task_initializes_progress() -> None:
    client = TestClient(app)
    resp = client.post("/api/tasks", json={"topic": "AI教育", "retrieval_depth": "L1"})
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["progress"] is not None
    assert task["progress"]["phase"] == "idle"
    assert task["outline_skeleton"] is None
