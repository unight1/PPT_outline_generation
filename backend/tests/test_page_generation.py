from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import tasks as tasks_route
from app.services import page_generation
from app.services.page_generation import (
    _build_page_prompt,
    _build_page_query,
    _clarification_text,
    clean_evidence_snippet,
    match_bullets_to_evidence,
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
    assert "AI改变教育模式" in prompt
    assert "paper.pdf" in prompt
    assert "https://example.com" in prompt
    assert "s1-b1" in prompt  # bullet_id template
    assert '"evidence_ids"' not in prompt
    assert "不要填写证据编号" in prompt


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


def test_retrieve_for_pages_uses_parallel_budgeted_tavily(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Hit:
        def __init__(self, idx: int) -> None:
            self.idx = idx

        def model_dump(self) -> dict:
            return {
                "snippet": f"证据{self.idx}",
                "source_id": "local",
                "locator": "L1",
                "score": 0.8,
                "confidence": 0.8,
            }

    class _Result:
        def __init__(self, idx: int) -> None:
            self.hits = [_Hit(idx)]

    class _Retriever:
        def __init__(self) -> None:
            self.depths: list[str] = []

        async def retrieve(self, request):  # type: ignore[no-untyped-def]
            self.depths.append(request.depth.value)
            return _Result(len(self.depths))

    retriever = _Retriever()
    monkeypatch.setattr(page_generation, "get_retriever", lambda **_: retriever)
    monkeypatch.setattr(page_generation.settings, "tavily_api_key", "tvly-test")
    monkeypatch.setattr(page_generation.settings, "retrieval_tavily_enabled", True)
    monkeypatch.setattr(page_generation.settings, "retrieval_tavily_max_pages", 2)
    monkeypatch.setattr(page_generation.settings, "retrieval_parallel_pages", 3)

    skeleton = [
        {"slide_id": "s1", "title": "页1"},
        {"slide_id": "s2", "title": "页2"},
        {"slide_id": "s3", "title": "页3"},
    ]
    result, _cache = page_generation.retrieve_for_pages("主题", "L1", skeleton, None)

    assert set(result) == {"s1", "s2", "s3"}
    assert retriever.depths.count("L1") == 2
    assert retriever.depths.count("L0") == 1


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


def test_slides_generate_accepts_failed_with_skeleton() -> None:
    task_id = _make_task_in_memory(
        status="failed",
        outline_skeleton=[{"slide_id": "s1", "title": "页1", "intent": "", "user_notes": ""}],
        clarification={"questions": [], "submitted": True},
    )
    tasks_route.TASK_STORE[task_id]["error"] = {
        "code": "LLM_ERROR",
        "message": "模型失败",
        "details": {"retryable": True, "phase": "llm_page", "slide_id": "s1"},
    }
    old_enqueue = tasks_route.enqueue_slides_generation
    tasks_route.enqueue_slides_generation = lambda tid, c: None  # type: ignore[assignment]
    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/tasks/{task_id}/slides/generate",
            json={"concurrency": 1, "force_refresh": True},
        )
        assert resp.status_code == 202
        stored = tasks_route.TASK_STORE[task_id]
        assert stored["status"] == "generating"
        assert stored["error"] is None
        assert stored["runtime"]["force_refresh_retrieval"] is True
    finally:
        tasks_route.enqueue_slides_generation = old_enqueue


def test_classify_slide_generation_exception_maps_workflow_error() -> None:
    from app.services.page_generation import SlideWorkflowError

    exc = SlideWorkflowError(
        "TAVILY_ERROR",
        "网络检索失败",
        slide_id="s2",
        phase="retrieving_page",
        reason="quota",
    )
    code, message, details = tasks_route.classify_slide_generation_exception(exc)
    assert code == "TAVILY_ERROR"
    assert message == "网络检索失败"
    assert details["slide_id"] == "s2"
    assert details["phase"] == "retrieving_page"
    assert details["retryable"] is True


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


def test_retrieve_for_pages_reuses_slide_cache() -> None:
    calls = {"count": 0}

    def _fake_uncached(topic, retrieval_depth, skeleton, clarification, *, tavily_enabled):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return {str(slide.get("slide_id")): [{"snippet": "x", "source_id": "s", "locator": "l"}] for slide in skeleton}

    page_generation._retrieve_for_pages_uncached = _fake_uncached  # type: ignore[method-assign]
    slide = {"slide_id": "s1", "title": "页1", "intent": "定义", "user_notes": ""}
    first, cache = page_generation.retrieve_for_pages("主题", "L1", [slide], None)
    second, cache2 = page_generation.retrieve_for_pages("主题", "L1", [slide], None, slide_cache=cache)
    assert calls["count"] == 1
    assert first["s1"][0]["snippet"] == second["s1"][0]["snippet"]
    assert cache2
    third, _ = page_generation.retrieve_for_pages(
        "主题", "L1", [slide], None, slide_cache=cache, force_refresh=True
    )
    assert calls["count"] == 2
    assert third["s1"]


def test_slides_generate_defaults_concurrency_when_payload_empty() -> None:
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
        resp = client.post(f"/api/tasks/{task_id}/slides/generate", json={})
        assert resp.status_code == 202
        assert captured_concurrency == [2]
        assert tasks_route.TASK_STORE[task_id]["runtime"]["concurrency"] == 2
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


# ── R1: clean_evidence_snippet ─────────────────────────────


def test_clean_evidence_snippet_normal_text() -> None:
    result = clean_evidence_snippet("AI在教育领域有广泛应用。据统计，2024年全球AI教育市场规模达到60亿美元。", max_chars=200)
    assert "AI" in result
    assert len(result) <= 200


def test_clean_evidence_snippet_filters_copyright() -> None:
    result = clean_evidence_snippet("Copyright © 2024 All Rights Reserved", max_chars=200)
    assert result == ""


def test_clean_evidence_snippet_filters_navigation() -> None:
    result = clean_evidence_snippet("首页 > 关于我们 > 联系我们 > 登录 > 注册", max_chars=200)
    assert result == ""


def test_clean_evidence_snippet_filters_disclaimer() -> None:
    result = clean_evidence_snippet("免责声明：本网站内容仅供参考", max_chars=200)
    assert result == ""


def test_clean_evidence_snippet_truncates_long_text() -> None:
    long_text = "这是第一句。" + "一些填充文本。" * 50
    result = clean_evidence_snippet(long_text, max_chars=200)
    assert len(result) <= 200


def test_clean_evidence_snippet_filters_nav_with_prefix() -> None:
    # e.g., "网站地图" pattern
    result = clean_evidence_snippet("网站地图", max_chars=200)
    assert result == ""


def test_clean_evidence_snippet_empty() -> None:
    assert clean_evidence_snippet("") == ""
    assert clean_evidence_snippet("   ") == ""


# ── R2: match_bullets_to_evidence ──────────────────────────


def test_match_bullets_high_overlap() -> None:
    bullets = [{"bullet_id": "b1", "text": "AI教育市场规模达60亿美元", "evidence_ids": []}]
    evidence = [{"evidence_id": "ev_1", "snippet": "2024年AI教育市场规模达60亿美元", "score": 0.9, "source_id": "report.pdf", "locator": "L1"}]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    assert result[0]["evidence_ids"] == ["ev_1"]
    assert low == 0


def test_match_bullets_low_overlap_gets_empty() -> None:
    bullets = [{"bullet_id": "b1", "text": "系统架构采用微服务设计", "evidence_ids": []}]
    evidence = [{"evidence_id": "ev_1", "snippet": "AI教育市场规模达60亿美元", "score": 0.9, "source_id": "report.pdf", "locator": "L1"}]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    assert result[0]["evidence_ids"] == []
    assert low == 1


def test_match_bullets_respects_existing_evidence_ids() -> None:
    bullets = [{"bullet_id": "b1", "text": "AI改变教育", "evidence_ids": ["ev_2"]}]
    evidence = [{"evidence_id": "ev_1", "snippet": "AI教育市场规模", "score": 0.9, "source_id": "r", "locator": "L1"}]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    assert result[0]["evidence_ids"] == ["ev_2"]
    assert low == 0


def test_match_bullets_no_evidence() -> None:
    bullets = [{"bullet_id": "b1", "text": "AI改变教育", "evidence_ids": []}]
    result, low = match_bullets_to_evidence(bullets, [], min_score=0.3)
    assert result[0]["evidence_ids"] == []
    assert low == 1


def test_match_bullets_partial_match() -> None:
    bullets = [
        {"bullet_id": "b1", "text": "AI市场规模", "evidence_ids": []},
        {"bullet_id": "b2", "text": "无关内容", "evidence_ids": []},
    ]
    evidence = [{"evidence_id": "ev_1", "snippet": "AI市场规模达60亿美元", "score": 0.9, "source_id": "r", "locator": "L1"}]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    assert result[0]["evidence_ids"] == ["ev_1"]
    assert result[1]["evidence_ids"] == []
    assert low == 1


# ── A2: LLM must not supply evidence_ids (backend binds later) ──


def test_generate_single_page_ignores_llm_evidence_ids(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(page_generation.settings, "use_real_llm", True)
    monkeypatch.setattr(page_generation.settings, "openai_api_key", "test-key")
    slide = {"slide_id": "s1", "title": "测试页", "intent": "", "user_notes": ""}
    evidence = [{"evidence_id": "ev_1", "snippet": "AI改变教育", "source_id": "p.pdf", "locator": "L1", "score": 0.9}]
    calls = []

    class _FakeResponse:
        class _Choice:
            message = type("msg", (), {"content": '{"bullets":[{"bullet_id":"s1-b1","text":"要点A","evidence_ids":["ev_1"]},{"bullet_id":"s1-b2","text":"要点B","evidence_ids":[]}],"speaker_notes":"备注"}'})()

        choices = [_Choice()]

    def _fake_create(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(1)
        return _FakeResponse()

    monkeypatch.setattr("openai.OpenAI", lambda **kw: type("client", (), {"chat": type("chat", (), {"completions": type("comp", (), {"create": _fake_create})()})()})())  # type: ignore[func-returns-value]
    monkeypatch.setattr(page_generation, "OpenAI", lambda **kw: type("client", (), {"chat": type("chat", (), {"completions": type("comp", (), {"create": _fake_create})()})()})())  # type: ignore[func-returns-value]

    from app.services.page_generation import _generate_single_page  # noqa: F811

    result = _generate_single_page("AI教育", slide, evidence)
    assert result["bullets"][0]["text"] == "要点A"
    assert result["bullets"][0]["evidence_ids"] == []
    assert result["bullets"][1]["evidence_ids"] == []


# ── R2: merge_pages uses matching not mechanical assignment ─


def test_merge_pages_uses_semantic_matching() -> None:
    skeleton = [{"slide_id": "s1", "title": "页", "intent": "", "user_notes": ""}]
    page_results = {
        "s1": {
            "slide_id": "s1", "title": "页",
            "bullets": [
                {"bullet_id": "s1-b1", "text": "AI市场规模", "evidence_ids": []},
                {"bullet_id": "s1-b2", "text": "微服务架构优势", "evidence_ids": []},
            ],
            "speaker_notes": "",
        }
    }
    retrieval = {
        "s1": [
            {"evidence_id": "ev_1", "snippet": "微服务架构提升了系统的可扩展性和部署灵活性", "source_id": "tech.md", "locator": "L3", "score": 0.85, "confidence": 0.7},
            {"evidence_id": "ev_2", "snippet": "AI教育市场规模达60亿美元", "source_id": "report.pdf", "locator": "L10", "score": 0.9, "confidence": 0.8},
        ],
    }
    outline = merge_pages_to_outline("test", skeleton, page_results, retrieval, "L1")
    slide = outline["slides"][0]
    # b1 about "AI市场规模" should match ev_2, b2 about "微服务架构" should match ev_1
    b1 = slide["bullets"][0]
    b2 = slide["bullets"][1]
    assert b1["evidence_ids"] == ["ev_2"]
    assert b2["evidence_ids"] == ["ev_1"]
    assert "low_confidence_bullets" in outline["meta"]


# ── R1 edge cases ───────────────────────────────────────────


def test_clean_evidence_snippet_all_noise_empty_catalog() -> None:
    """When all evidence hits are noise, evidence_catalog skips them."""
    skeleton = [{"slide_id": "s1", "title": "页", "intent": "", "user_notes": ""}]
    page_results = {
        "s1": {
            "slide_id": "s1", "title": "页",
            "bullets": [{"bullet_id": "s1-b1", "text": "需要证据", "evidence_ids": []}],
            "speaker_notes": "",
        }
    }
    retrieval = {
        "s1": [
            {"evidence_id": "ev_1", "snippet": "网站地图", "source_id": "n1", "locator": "L1", "score": 0.5},
            {"evidence_id": "ev_2", "snippet": "Copyright © 2024", "source_id": "n2", "locator": "L2", "score": 0.5},
        ],
    }
    outline = merge_pages_to_outline("test", skeleton, page_results, retrieval, "L0")
    assert outline["evidence_catalog"] == []
    assert outline["meta"]["evidence_coverage_total"] == 0


def test_clean_evidence_snippet_mixed_noise_and_valid() -> None:
    """Valid snippets survive, noise is dropped."""
    skeleton = [{"slide_id": "s1", "title": "页", "intent": "", "user_notes": ""}]
    page_results = {
        "s1": {
            "slide_id": "s1", "title": "页",
            "bullets": [{"bullet_id": "s1-b1", "text": "市场规模", "evidence_ids": []}],
            "speaker_notes": "",
        }
    }
    retrieval = {
        "s1": [
            {"evidence_id": "ev_1", "snippet": "网站地图", "source_id": "noise", "locator": "L1", "score": 0.9},
            {"evidence_id": "ev_2", "snippet": "2024年AI市场规模达60亿美元", "source_id": "real", "locator": "L2", "score": 0.85},
        ],
    }
    outline = merge_pages_to_outline("test", skeleton, page_results, retrieval, "L0")
    assert len(outline["evidence_catalog"]) == 1
    assert outline["evidence_catalog"][0]["evidence_id"] == "ev_2"


# ── R2 English text matching ────────────────────────────────


def test_match_bullets_english_text() -> None:
    bullets = [
        {"bullet_id": "b1", "text": "Neural networks improve accuracy significantly", "evidence_ids": []},
        {"bullet_id": "b2", "text": "Cloud infrastructure reduces operational costs", "evidence_ids": []},
    ]
    evidence = [
        {"evidence_id": "ev_1", "snippet": "Cloud platforms reduce infrastructure costs by 30 percent", "score": 0.9, "source_id": "r1", "locator": "L1"},
        {"evidence_id": "ev_2", "snippet": "Deep neural networks achieve state-of-the-art accuracy in image recognition", "score": 0.85, "source_id": "r2", "locator": "L2"},
    ]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    assert result[0]["evidence_ids"] == ["ev_2"], f"b1 should match neural nets ev_2, got {result[0]['evidence_ids']}"
    assert result[1]["evidence_ids"] == ["ev_1"], f"b2 should match cloud ev_1, got {result[1]['evidence_ids']}"
    assert low == 0


def test_match_bullets_english_low_overlap() -> None:
    bullets = [{"bullet_id": "b1", "text": "Machine learning applications in healthcare", "evidence_ids": []}]
    evidence = [{"evidence_id": "ev_1", "snippet": "Stock market trends in Q4 2024 show growth", "score": 0.9, "source_id": "r1", "locator": "L1"}]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    # Very low character overlap → should not match
    assert result[0]["evidence_ids"] == []
    assert low == 1


# ── R2 mixed Chinese-English evidence ───────────────────────


def test_match_bullets_mixed_language() -> None:
    bullets = [{"bullet_id": "b1", "text": "Transformer模型在NLP任务中表现优异", "evidence_ids": []}]
    evidence = [
        {"evidence_id": "ev_1", "snippet": "LSTM networks were dominant before Transformer architecture", "score": 0.8, "source_id": "en", "locator": "L1"},
        {"evidence_id": "ev_2", "snippet": "Transformer模型通过自注意力机制大幅提升了NLP性能", "score": 0.9, "source_id": "zh", "locator": "L2"},
    ]
    result, low = match_bullets_to_evidence(bullets, evidence, min_score=0.3)
    # Should match ev_2 (Chinese overlap with Transformer, 模型, NLP) over ev_1
    assert result[0]["evidence_ids"] == ["ev_2"]
    assert low == 0


# ── R1 edge: long snippet with noise prefix ──────────────────


def test_clean_evidence_snippet_truncates_at_sentence_boundary() -> None:
    # Long enough to need truncation, each sentence is ~20 chars
    snippet = ("据统计2024年AI市场规模达60亿美元且保持增长趋势。" +
               "全行业增长迅速体现技术变革与政策支持的协同效应。" * 15)
    result = clean_evidence_snippet(snippet, max_chars=80)
    assert 0 < len(result) <= 80


def test_clean_evidence_snippet_preserves_fact_sentences() -> None:
    snippet = "首页。联系我们。据统计2024年AI市场规模达60亿美元。全行业增长迅速。"
    result = clean_evidence_snippet(snippet, max_chars=200)
    # Nav-like sentences should be dropped, facts kept
    assert "据统计" in result
    assert "全行业增长迅速" in result
    assert "首页" not in result or "联系我们" not in result

