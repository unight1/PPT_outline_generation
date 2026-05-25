from __future__ import annotations

from concurrent.futures import Future

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.api.routes import tasks as tasks_route


def _done_future() -> Future[None]:
    fut: Future[None] = Future()
    fut.set_result(None)
    return fut


def _sync_enqueue(task_id: str) -> Future[None]:
    tasks_route.complete_generation(task_id)
    return _done_future()


def _sync_enqueue_skeleton(task_id: str) -> Future[None]:
    tasks_route.complete_skeleton_generation(task_id)
    return _done_future()


def setup_function() -> None:
    tasks_route.TASK_STORE.clear()
    tasks_route.USE_DB_STORE = False
    settings.use_real_llm = False


def test_create_task_starts_in_clarifying() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/tasks",
        json={"topic": "AI PPT", "retrieval_depth": "L1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "clarifying"

    task_id = data["task_id"]
    task_resp = client.get(f"/api/tasks/{task_id}")
    assert task_resp.status_code == 200
    task = task_resp.json()
    assert task["status"] == "clarifying"
    assert "schema_version" in task
    assert task["clarification"]["submitted"] is False
    assert len(task["clarification"]["questions"]) >= 6


def test_clarification_questions_are_trimmed_when_context_is_complete() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/tasks",
        json={
            "topic": "AI PPT",
            "retrieval_depth": "L1",
            "audience": "本科生课堂",
            "raw_notes": "必须包含案例，避免空泛术语",
        },
    )
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    ids = [q["question_id"] for q in task["clarification"]["questions"]]
    assert "audience_level" not in ids
    assert "constraints" not in ids
    assert "goal" in ids and "style" in ids and "depth" in ids


def test_generate_requires_submitted_clarification() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L1"}).json()
    task_id = create["task_id"]

    generate = client.post(f"/api/tasks/{task_id}/generate", json={})
    assert generate.status_code == 409
    assert generate.json()["error"]["code"] == "INVALID_STATE"


def test_submit_clarification_then_generate_done() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]

    patch = client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={
            "answers": [{"question_id": "goal", "answer": "让同学理解方案价值"}],
            "submitted": True,
        },
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "pending"

    old_enqueue = tasks_route.enqueue_generation
    old_orch = tasks_route.generate_outline_with_research
    tasks_route.enqueue_generation = _sync_enqueue
    tasks_route.generate_outline_with_research = lambda **_: {  # type: ignore[assignment]
        "title": "Demo",
        "slides": [
            {
                "slide_id": "s1",
                "title": "页1",
                "bullets": [{"bullet_id": "s1-b1", "text": "要点", "evidence_ids": []}],
                "speaker_notes": "",
            }
        ],
        "evidence_catalog": [],
        "meta": {"retrieval_depth": "L0", "generated_at": "2026-01-01T00:00:00Z"},
    }
    try:
        generate = client.post(f"/api/tasks/{task_id}/generate", json={})
        assert generate.status_code == 202

        task_resp = client.get(f"/api/tasks/{task_id}")
        assert task_resp.status_code == 200
        task = task_resp.json()
        assert task["status"] == "done"
        assert task["outline"] is not None
    finally:
        tasks_route.enqueue_generation = old_enqueue
        tasks_route.generate_outline_with_research = old_orch


def test_generate_and_patch_outline_skeleton() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]
    client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={
            "answers": [
                {"question_id": "goal", "answer": "说明系统价值"},
                {"question_id": "page_range", "answer": "6 页"},
            ],
            "submitted": True,
        },
    )

    old_enqueue = tasks_route.enqueue_skeleton_generation
    tasks_route.enqueue_skeleton_generation = _sync_enqueue_skeleton
    try:
        generate = client.post(f"/api/tasks/{task_id}/skeleton/generate", json={})
        assert generate.status_code == 202
        task = client.get(f"/api/tasks/{task_id}").json()
        assert task["status"] == "pending"
        assert task["progress"]["phase"] == "skeleton_ready"
        assert len(task["outline_skeleton"]) == 6

        slides = task["outline_skeleton"]
        slides[0]["title"] = "用户确认后的第一页"
        slides[0]["user_notes"] = "强调课程项目背景"
        patch = client.patch(f"/api/tasks/{task_id}/skeleton", json={"slides": slides})
        assert patch.status_code == 200
        patched = patch.json()
        assert patched["outline_skeleton"][0]["title"] == "用户确认后的第一页"
        assert patched["outline_skeleton"][0]["user_notes"] == "强调课程项目背景"
    finally:
        tasks_route.enqueue_skeleton_generation = old_enqueue


def test_generate_skeleton_requires_submitted_clarification() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]

    resp = client.post(f"/api/tasks/{task_id}/skeleton/generate", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"


def test_patch_skeleton_after_failed_resets_to_pending() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]
    task = tasks_route.TASK_STORE[task_id]
    task["status"] = "failed"
    task["clarification"]["submitted"] = True
    task["outline_skeleton"] = [{"slide_id": "s1", "title": "旧页", "intent": "", "user_notes": ""}]
    task["error"] = {"code": "INTERNAL_ERROR", "message": "old failure", "details": {}}

    resp = client.patch(
        f"/api/tasks/{task_id}/skeleton",
        json={"slides": [{"slide_id": "s1", "title": "重试页", "intent": "重新生成", "user_notes": ""}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["error"] is None
    assert body["outline_skeleton"][0]["title"] == "重试页"
    assert body["progress"]["phase"] == "skeleton_ready"


def test_patch_outline_merges_slides_and_rebuilds_evidence_map() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]
    task = tasks_route.TASK_STORE[task_id]
    task["status"] = "done"
    task["outline"] = {
        "title": "旧标题",
        "slides": [
            {
                "slide_id": "s1",
                "title": "第一页",
                "bullets": [{"bullet_id": "s1-b1", "text": "旧要点", "evidence_ids": ["ev_1"]}],
                "speaker_notes": "",
            },
            {
                "slide_id": "s2",
                "title": "第二页",
                "bullets": [{"bullet_id": "s2-b1", "text": "保留要点", "evidence_ids": []}],
                "speaker_notes": "",
            },
        ],
        "evidence_catalog": [
            {"evidence_id": "ev_1", "snippet": "旧证据", "source_id": "old", "locator": "L1", "score": 0.5, "confidence": 0.5}
        ],
        "page_evidence_map": [],
        "meta": {"retrieval_depth": "L0"},
    }

    resp = client.patch(
        f"/api/tasks/{task_id}/outline",
        json={
            "title": "新标题",
            "slides": [
                {
                    "slide_id": "s1",
                    "title": "第一页修改",
                    "bullets": [{"bullet_id": "s1-b1", "text": "新要点", "evidence_ids": ["ev_2"]}],
                    "speaker_notes": "新备注",
                }
            ],
            "evidence_catalog": [
                {"evidence_id": "ev_2", "snippet": "新证据", "source_id": "new", "locator": "L2", "score": 0.9, "confidence": 0.8}
            ],
        },
    )

    assert resp.status_code == 200
    patched = resp.json()
    assert patched["outline"]["title"] == "新标题"
    assert patched["outline"]["slides"][0]["title"] == "第一页修改"
    assert patched["outline"]["slides"][1]["title"] == "第二页"
    assert patched["outline"]["page_evidence_map"][0]["evidence_trace"][0]["evidence_id"] == "ev_2"
    assert patched["progress"]["phase"] == "done"


def test_patch_outline_rejects_before_done() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]

    resp = client.patch(f"/api/tasks/{task_id}/outline", json={"title": "新标题"})

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"


def test_patch_clarification_rejected_after_done() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]

    client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={"answers": [{"question_id": "goal", "answer": "A"}], "submitted": True},
    )

    old_enqueue = tasks_route.enqueue_generation
    old_orch = tasks_route.generate_outline_with_research
    tasks_route.enqueue_generation = _sync_enqueue
    tasks_route.generate_outline_with_research = lambda **_: {  # type: ignore[assignment]
        "title": "Demo",
        "slides": [],
        "evidence_catalog": [],
        "meta": {"retrieval_depth": "L0", "generated_at": "2026-01-01T00:00:00Z"},
    }
    try:
        client.post(f"/api/tasks/{task_id}/generate", json={})
    finally:
        tasks_route.enqueue_generation = old_enqueue
        tasks_route.generate_outline_with_research = old_orch

    patch_again = client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={"answers": [{"question_id": "goal", "answer": "B"}]},
    )
    assert patch_again.status_code == 409
    assert patch_again.json()["error"]["code"] == "INVALID_STATE"


def test_list_tasks_with_status_filter() -> None:
    client = TestClient(app)
    for idx in range(2):
        client.post("/api/tasks", json={"topic": f"AI PPT {idx}", "retrieval_depth": "L1"})

    listed = client.get("/api/tasks", params={"status_filter": "clarifying", "limit": 10})
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 2
    assert all(task["status"] == "clarifying" for task in body["tasks"])


def test_generate_is_idempotent_when_already_generating() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]
    client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={"answers": [{"question_id": "goal", "answer": "A"}], "submitted": True},
    )

    old_enqueue = tasks_route.enqueue_generation
    old_orch = tasks_route.generate_outline_with_research
    hold = Future()
    tasks_route.enqueue_generation = lambda _: hold  # type: ignore[assignment]
    tasks_route.generate_outline_with_research = lambda **_: {  # type: ignore[assignment]
        "title": "Demo",
        "slides": [],
        "evidence_catalog": [],
        "meta": {"retrieval_depth": "L0", "generated_at": "2026-01-01T00:00:00Z"},
    }
    try:
        first = client.post(f"/api/tasks/{task_id}/generate", json={})
        assert first.status_code == 202
        assert first.json()["idempotent"] is False

        second = client.post(f"/api/tasks/{task_id}/generate", json={})
        assert second.status_code == 202
        assert second.json()["status"] == "generating"
        assert second.json()["idempotent"] is True
    finally:
        tasks_route.enqueue_generation = old_enqueue
        tasks_route.generate_outline_with_research = old_orch
        hold.set_result(None)


def test_same_idempotency_key_in_pending_still_starts_generation() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]
    client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={"answers": [{"question_id": "goal", "answer": "A"}], "submitted": True},
    )

    called: list[str] = []
    old_enqueue = tasks_route.enqueue_generation
    tasks_route.enqueue_generation = lambda tid: called.append(tid) or _done_future()  # type: ignore[assignment]
    try:
        resp = client.post(
            f"/api/tasks/{task_id}/generate",
            json={"idempotency_key": "same-key"},
        )
        assert resp.status_code == 202
        assert resp.json()["idempotent"] is False
        assert called == [task_id]
    finally:
        tasks_route.enqueue_generation = old_enqueue


def test_long_document_requires_document_text() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/tasks",
        json={
            "topic": "长文档测试",
            "source_type": "long_document",
            "retrieval_depth": "L1",
        },
    )
    assert resp.status_code == 422


def test_long_document_builds_internal_document_profile() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/tasks",
        json={
            "topic": "长文档测试",
            "source_type": "long_document",
            "document_text": "这是一个很长的文档内容。 " * 200,
            "document_title": "白皮书草稿",
            "retrieval_depth": "L1",
        },
    )
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]
    stored = tasks_route.TASK_STORE[task_id]
    profile = stored["input"].get("document_profile")
    assert isinstance(profile, dict)
    assert profile.get("char_count", 0) > 0
    assert profile.get("segment_count", 0) > 0
    assert isinstance(profile.get("key_points"), list)
    assert isinstance(profile.get("keywords"), list)


def test_task_not_found_returns_contract_error() -> None:
    client = TestClient(app)
    missing_id = "00000000-0000-4000-8000-000000000099"
    resp = client.get(f"/api/tasks/{missing_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_invalid_task_id_returns_client_error() -> None:
    client = TestClient(app)
    resp = client.get("/api/tasks/not-a-uuid")
    # FastAPI path param {task_id:uuid} rejects non-UUID before our handler (404).
    assert resp.status_code in (404, 422)


def test_create_task_empty_topic_returns_validation_error() -> None:
    client = TestClient(app)
    resp = client.post("/api/tasks", json={"topic": "", "retrieval_depth": "L1"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_long_document_generation_passes_document_profile_to_orchestration() -> None:
    client = TestClient(app)
    document_text = "远程医疗平台可提升基层诊断效率。" * 80
    create = client.post(
        "/api/tasks",
        json={
            "topic": "远程医疗",
            "source_type": "long_document",
            "document_text": document_text,
            "document_title": "行业报告",
            "retrieval_depth": "L0",
        },
    ).json()
    task_id = create["task_id"]
    client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={"answers": [{"question_id": "goal", "answer": "说明价值"}], "submitted": True},
    )

    captured: dict = {}

    def _capture(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {
            "title": "远程医疗大纲",
            "slides": [
                {
                    "slide_id": "s1",
                    "title": "页1",
                    "bullets": [{"bullet_id": "s1-b1", "text": "要点", "evidence_ids": []}],
                    "speaker_notes": "",
                }
            ],
            "evidence_catalog": [],
            "meta": {"retrieval_depth": "L0", "generated_at": "2026-01-01T00:00:00Z"},
        }

    old_enqueue = tasks_route.enqueue_generation
    old_orch = tasks_route.generate_outline_with_research
    tasks_route.enqueue_generation = _sync_enqueue
    tasks_route.generate_outline_with_research = _capture  # type: ignore[assignment]
    try:
        client.post(f"/api/tasks/{task_id}/generate", json={})
        profile = captured.get("document_profile")
        assert isinstance(profile, dict)
        assert profile.get("segment_count", 0) > 0
        assert captured.get("source_type") == "long_document"
    finally:
        tasks_route.enqueue_generation = old_enqueue
        tasks_route.generate_outline_with_research = old_orch


def test_recover_inflight_generations_marks_stale_and_requeues() -> None:
    tasks_route.TASK_STORE["t-1"] = {
        "task_id": "t-1",
        "schema_version": "v0.2.0",
        "status": "generating",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "input": {"topic": "x", "retrieval_depth": "L0", "raw_notes": None},
        "clarification": {"questions": [], "submitted": True},
        "outline": None,
        "error": None,
        "runtime": {"generation_attempts": 1, "last_started_at": "2026-01-01T00:00:00+00:00"},
    }

    called: list[str] = []
    old_enqueue = tasks_route.enqueue_generation
    tasks_route.enqueue_generation = lambda task_id: called.append(task_id) or _done_future()  # type: ignore[assignment]
    try:
        recovered = tasks_route.recover_inflight_generations(limit=10)
        assert recovered == 1
        assert called == ["t-1"]
        assert tasks_route.TASK_STORE["t-1"]["status"] == "pending"
        assert tasks_route.TASK_STORE["t-1"]["error"]["code"] == "INTERNAL_ERROR"
    finally:
        tasks_route.enqueue_generation = old_enqueue


def test_recover_inflight_generations_requeues_skeleton_and_slides() -> None:
    base = {
        "schema_version": "v1.0.0",
        "status": "generating",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "input": {"topic": "x", "retrieval_depth": "L0", "raw_notes": None},
        "clarification": {"questions": [], "submitted": True},
        "outline": None,
        "outline_skeleton": [{"slide_id": "s1", "title": "页1", "intent": "", "user_notes": ""}],
        "error": None,
    }
    tasks_route.TASK_STORE["skeleton-task"] = {
        **base,
        "task_id": "skeleton-task",
        "runtime": {"workflow": "skeleton"},
        "progress": {"phase": "skeleton_llm", "current": None, "total": None, "message": "", "percent": None},
    }
    tasks_route.TASK_STORE["slides-task"] = {
        **base,
        "task_id": "slides-task",
        "runtime": {"workflow": "slides", "concurrency": 2},
        "progress": {"phase": "llm_page", "current": 1, "total": 1, "message": "", "percent": 50},
    }

    skeleton_called: list[str] = []
    slides_called: list[str] = []
    old_enqueue_skeleton = tasks_route.enqueue_skeleton_generation
    old_enqueue_slide = tasks_route.enqueue_slide_generation
    tasks_route.enqueue_skeleton_generation = lambda task_id: skeleton_called.append(task_id) or _done_future()  # type: ignore[assignment]
    tasks_route.enqueue_slide_generation = lambda task_id: slides_called.append(task_id) or _done_future()  # type: ignore[assignment]
    try:
        recovered = tasks_route.recover_inflight_generations(limit=10)
        assert recovered == 2
        assert skeleton_called == ["skeleton-task"]
        assert slides_called == ["slides-task"]
        assert tasks_route.TASK_STORE["skeleton-task"]["status"] == "pending"
        assert tasks_route.TASK_STORE["slides-task"]["status"] == "pending"
    finally:
        tasks_route.enqueue_skeleton_generation = old_enqueue_skeleton
        tasks_route.enqueue_slide_generation = old_enqueue_slide


def test_retry_failed_task_accepts_only_failed() -> None:
    client = TestClient(app)
    create = client.post("/api/tasks", json={"topic": "AI PPT", "retrieval_depth": "L0"}).json()
    task_id = create["task_id"]
    not_failed_retry = client.post(f"/api/tasks/{task_id}/retry", json={})
    assert not_failed_retry.status_code == 409

    client.patch(
        f"/api/tasks/{task_id}/clarification",
        json={"answers": [{"question_id": "goal", "answer": "A"}], "submitted": True},
    )
    old_enqueue = tasks_route.enqueue_generation
    tasks_route.enqueue_generation = lambda _: _done_future()  # type: ignore[assignment]
    old_complete = tasks_route.complete_generation
    tasks_route.complete_generation = lambda _: None  # type: ignore[assignment]
    try:
        # Manually set failed to simulate retry scenario.
        task = tasks_route.TASK_STORE[task_id]
        task["status"] = "failed"
        task["error"] = {"code": "INTERNAL_ERROR", "message": "x", "details": {}}
        ok_retry = client.post(f"/api/tasks/{task_id}/retry", json={})
        assert ok_retry.status_code == 202
        assert ok_retry.json()["accepted"] is True
    finally:
        tasks_route.enqueue_generation = old_enqueue
        tasks_route.complete_generation = old_complete


def test_export_tasks_endpoint_not_shadowed_by_task_id_route() -> None:
    client = TestClient(app)
    client.post("/api/tasks", json={"topic": "topic1", "retrieval_depth": "L1"})
    export_resp = client.get("/api/tasks/export", params={"status_filter": "clarifying", "limit": 20})
    assert export_resp.status_code == 200
    body = export_resp.json()
    assert "tasks" in body
