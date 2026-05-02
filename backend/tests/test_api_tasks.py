from __future__ import annotations

from concurrent.futures import Future

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import tasks as tasks_route


def _done_future() -> Future[None]:
    fut: Future[None] = Future()
    fut.set_result(None)
    return fut


def _sync_enqueue(task_id: str) -> Future[None]:
    tasks_route.complete_generation(task_id)
    return _done_future()


def setup_function() -> None:
    tasks_route.TASK_STORE.clear()
    tasks_route.USE_DB_STORE = False


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
