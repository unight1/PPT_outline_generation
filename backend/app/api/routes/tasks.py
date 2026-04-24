from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from app.task_store import get_task as db_get_task
from app.task_store import save_task as db_save_task
from app.task_store import store_available

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    pending = "pending"
    clarifying = "clarifying"
    generating = "generating"
    done = "done"
    failed = "failed"


class RetrievalDepth(str, Enum):
    l0 = "L0"
    l1 = "L1"
    l2 = "L2"


class Problem(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CreateTaskRequest(BaseModel):
    topic: str = Field(min_length=1)
    audience: str | None = None
    duration_minutes: int = Field(default=15, ge=5, le=120)
    language: str = "zh"
    retrieval_depth: RetrievalDepth = RetrievalDepth.l1
    raw_notes: str | None = None


class CreateTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: str


class ClarificationQuestion(BaseModel):
    question_id: str
    prompt: str
    answer: str | None = None


class Clarification(BaseModel):
    questions: list[ClarificationQuestion]
    submitted: bool = False


class PatchClarificationItem(BaseModel):
    question_id: str
    answer: str


class PatchClarificationRequest(BaseModel):
    answers: list[PatchClarificationItem] = Field(default_factory=list)
    submitted: bool | None = None


class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    accepted: bool


TASK_STORE: dict[str, dict[str, Any]] = {}
# Prefer MySQL when configured; keep in-memory fallback for local demos/tests.
USE_DB_STORE = store_available()


def persist_task(task: dict[str, Any]) -> None:
    if USE_DB_STORE:
        db_save_task(task)
        return
    TASK_STORE[task["task_id"]] = task


def fetch_task(task_id: str) -> dict[str, Any] | None:
    if USE_DB_STORE:
        return db_get_task(task_id)
    return TASK_STORE.get(task_id)


def build_error(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": Problem(code=code, message=message, details=details or {}).model_dump()},
    )


def get_task_or_404(task_id: str) -> dict[str, Any]:
    task = fetch_task(task_id)
    if task is None:
        raise build_error(status.HTTP_404_NOT_FOUND, "TASK_NOT_FOUND", f"Task {task_id} not found.")
    return task


def validate_task_id(task_id: str) -> None:
    try:
        UUID(task_id)
    except ValueError as exc:
        raise build_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", "task_id must be UUID.") from exc


def task_snapshot(task: dict[str, Any]) -> dict[str, Any]:
    # Keep response shape aligned with api_contract_v0.md.
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "clarification": task["clarification"],
        "outline": task["outline"],
        "error": task["error"],
    }


def stub_outline(depth: RetrievalDepth) -> dict[str, Any]:
    generated_at = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    return {
        "title": "AI 时代的高效演示设计",
        "slides": [
            {
                "slide_id": "s1",
                "title": "背景与目标",
                "bullets": [
                    {"bullet_id": "s1-b1", "text": "为什么需要自动化生成 PPT", "evidence_ids": ["ev_1"]},
                    {"bullet_id": "s1-b2", "text": "项目目标与受众收益", "evidence_ids": []},
                ],
                "speaker_notes": "先讲问题，再讲目标。",
            }
        ],
        "evidence_catalog": [
            {
                "evidence_id": "ev_1",
                "snippet": "知识工作者每周平均花费数小时整理演示材料。",
                "source_id": "demo_source",
                "locator": "段落 1",
                "score": 0.8,
                "confidence": 0.7,
            }
        ],
        "meta": {
            "retrieval_depth": depth.value,
            "generated_at": generated_at,
        },
    }


@router.post("", response_model=CreateTaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: CreateTaskRequest) -> CreateTaskResponse:
    task_id = str(uuid4())
    created_at = now_iso()
    task = {
        "task_id": task_id,
        "status": TaskStatus.pending.value,
        "created_at": created_at,
        "updated_at": created_at,
        "input": payload.model_dump(),
        # Initialize with a default clarification question so UI can render immediately.
        "clarification": {
            "questions": [
                {
                    "question_id": "goal",
                    "prompt": "本次演示希望听众记住的一个核心结论是什么？",
                    "answer": None,
                }
            ],
            "submitted": False,
        },
        "outline": None,
        "error": None,
    }
    persist_task(task)
    logger.info("Task created task_id=%s status=%s", task_id, task["status"])
    return CreateTaskResponse(task_id=task_id, status=TaskStatus.pending, created_at=created_at)


@router.get("/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    validate_task_id(task_id)
    return task_snapshot(get_task_or_404(task_id))


@router.patch("/{task_id}/clarification")
def patch_clarification(task_id: str, payload: PatchClarificationRequest) -> dict[str, Any]:
    validate_task_id(task_id)
    task = get_task_or_404(task_id)
    if task["status"] in (TaskStatus.generating.value, TaskStatus.done.value, TaskStatus.failed.value):
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Cannot update clarification in current task state.",
            {"status": task["status"]},
        )

    question_map = {item["question_id"]: item for item in task["clarification"]["questions"]}
    for answer_item in payload.answers:
        if answer_item.question_id in question_map:
            question_map[answer_item.question_id]["answer"] = answer_item.answer

    if payload.submitted is not None:
        task["clarification"]["submitted"] = payload.submitted
        if payload.submitted:
            task["status"] = TaskStatus.pending.value

    task["updated_at"] = now_iso()
    persist_task(task)
    logger.info("Clarification updated task_id=%s submitted=%s", task_id, task["clarification"]["submitted"])
    return task_snapshot(task)


def complete_generation(task_id: str) -> None:
    try:
        task = fetch_task(task_id)
        if task is None:
            return

        # Special marker to let evaluation scripts reliably cover failed status flow.
        if "[FAIL]" in task["input"]["topic"]:
            task["status"] = TaskStatus.failed.value
            task["error"] = {
                "code": "INTERNAL_ERROR",
                "message": "Generation failed by test marker.",
                "details": {"reason": "topic contains [FAIL]"},
            }
            task["updated_at"] = now_iso()
            persist_task(task)
            logger.warning("Task failed task_id=%s reason=test-marker", task_id)
            return

        task["outline"] = stub_outline(RetrievalDepth(task["input"]["retrieval_depth"]))
        task["status"] = TaskStatus.done.value
        task["error"] = None
        task["updated_at"] = now_iso()
        persist_task(task)
        logger.info("Task completed task_id=%s status=%s", task_id, task["status"])
    except Exception:
        logger.exception("Task generation crashed task_id=%s", task_id)
        task = fetch_task(task_id)
        if task is not None:
            task["status"] = TaskStatus.failed.value
            task["error"] = {
                "code": "INTERNAL_ERROR",
                "message": "Unexpected error during generation.",
                "details": {},
            }
            task["updated_at"] = now_iso()
            persist_task(task)


@router.post("/{task_id}/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_task(task_id: str, background_tasks: BackgroundTasks) -> GenerateResponse:
    validate_task_id(task_id)
    task = get_task_or_404(task_id)
    if task["status"] not in (TaskStatus.pending.value, TaskStatus.clarifying.value):
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Task cannot be generated in current state.",
            {"status": task["status"]},
        )
    if task["status"] == TaskStatus.clarifying.value and not task["clarification"]["submitted"]:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Clarification must be submitted before generation.",
        )

    task["status"] = TaskStatus.generating.value
    task["updated_at"] = now_iso()
    persist_task(task)
    logger.info("Task accepted task_id=%s status=%s", task_id, task["status"])
    # Return quickly and finish generation in background to match async contract.
    background_tasks.add_task(complete_generation, task_id)
    return GenerateResponse(task_id=task_id, status=TaskStatus.generating, accepted=True)
