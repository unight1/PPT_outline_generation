from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.task_store import get_task as db_get_task
from app.task_store import list_tasks as db_list_tasks
from app.task_store import list_tasks_by_status as db_list_tasks_by_status
from app.task_store import save_task as db_save_task
from app.task_store import store_available
from app.services.document_processing import build_document_profile
from app.services.generation import should_force_fail
from app.services.orchestration import generate_outline_with_research

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
    source_type: Literal["short_topic", "long_document"] = "short_topic"
    audience: str | None = None
    duration_minutes: int = Field(default=15, ge=5, le=120)
    language: str = "zh"
    retrieval_depth: RetrievalDepth = RetrievalDepth.l1
    raw_notes: str | None = None
    document_text: str | None = None
    document_title: str | None = None

    @model_validator(mode="after")
    def validate_long_document_input(self) -> "CreateTaskRequest":
        if self.source_type == "long_document" and not (self.document_text or "").strip():
            raise ValueError("document_text is required when source_type=long_document")
        return self


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
    idempotent: bool = False


class ListTasksResponse(BaseModel):
    tasks: list[dict[str, Any]]
    total: int


class GenerateTaskRequest(BaseModel):
    idempotency_key: str | None = None


TASK_STORE: dict[str, dict[str, Any]] = {}
# Prefer MySQL when configured; keep in-memory fallback for local demos/tests.
USE_DB_STORE = store_available()
GENERATION_EXECUTOR = ThreadPoolExecutor(max_workers=settings.generation_worker_max_workers)


class GenerationTimeoutError(RuntimeError):
    pass


def _estimate_page_range(duration_minutes: int) -> str:
    low = max(5, duration_minutes // 2)
    high = max(low + 2, duration_minutes)
    return f"{low}-{high} 页"


def build_default_clarification_questions(payload: CreateTaskRequest) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    questions.extend(
        [
            {
                "question_id": "goal",
                "prompt": "本次演示希望听众记住的一个核心结论是什么？",
                "answer": None,
            },
            {
                "question_id": "style",
                "prompt": "希望表达风格偏正式汇报、课堂讲解还是路演展示？",
                "answer": None,
            },
            {
                "question_id": "depth",
                "prompt": "内容深度偏概览、实操还是研究分析？",
                "answer": None,
            },
        ]
    )
    if not (payload.audience or "").strip():
        questions.append(
            {
                "question_id": "audience_level",
                "prompt": "听众对该主题的熟悉程度如何（入门/中等/专业）？",
                "answer": None,
            }
        )
    if not (payload.raw_notes or "").strip():
        questions.append(
            {
                "question_id": "constraints",
                "prompt": "是否有必须包含或必须避免的内容约束？",
                "answer": None,
            }
        )
    if payload.source_type == "long_document" and not (payload.document_title or "").strip():
        questions.append(
            {
                "question_id": "doc_focus",
                "prompt": "长文档中优先提炼哪些章节或观点？",
                "answer": None,
            }
        )
    questions.append(
        {
            "question_id": "page_range",
            "prompt": "期望页数范围是多少（例如 8-12 页）？",
            "answer": _estimate_page_range(payload.duration_minutes),
        }
    )
    return questions


def persist_task(task: dict[str, Any]) -> None:
    if USE_DB_STORE:
        db_save_task(task)
        return
    TASK_STORE[task["task_id"]] = task


def fetch_task(task_id: str) -> dict[str, Any] | None:
    if USE_DB_STORE:
        return db_get_task(task_id)
    return TASK_STORE.get(task_id)


def fetch_tasks_by_status(status: TaskStatus, limit: int = 100) -> list[dict[str, Any]]:
    if USE_DB_STORE:
        return db_list_tasks_by_status(status=status.value, limit=limit)
    tasks = [task for task in TASK_STORE.values() if task.get("status") == status.value]
    tasks.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return tasks[:limit]


def enqueue_generation(task_id: str) -> Future[None]:
    return GENERATION_EXECUTOR.submit(complete_generation, task_id)


def classify_generation_exception(exc: Exception) -> tuple[str, str, dict[str, Any]]:
    message = str(exc)
    if isinstance(exc, GenerationTimeoutError):
        return (
            "GENERATION_TIMEOUT",
            "Generation exceeded timeout budget.",
            {"retryable": True, "reason": "hard-timeout"},
        )
    lowered = message.lower()
    if "timeout" in lowered:
        return (
            "GENERATION_TIMEOUT",
            "Generation timed out in upstream model or retrieval.",
            {"retryable": True, "reason": "upstream-timeout"},
        )
    if "chroma" in lowered or "embedding" in lowered or "retriev" in lowered:
        return (
            "RETRIEVAL_UNAVAILABLE",
            "Retrieval subsystem is unavailable.",
            {"retryable": True},
        )
    return ("INTERNAL_ERROR", "Unexpected error during generation.", {"retryable": True})


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
        "schema_version": task.get("schema_version", settings.task_schema_version),
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "clarification": task["clarification"],
        "outline": task["outline"],
        "error": task["error"],
    }


@router.post("", response_model=CreateTaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: CreateTaskRequest) -> CreateTaskResponse:
    task_id = str(uuid4())
    created_at = now_iso()
    input_payload = payload.model_dump()
    if payload.source_type == "long_document":
        input_payload["document_profile"] = build_document_profile(payload.document_text)
    task = {
        "task_id": task_id,
        "schema_version": settings.task_schema_version,
        "status": TaskStatus.clarifying.value,
        "created_at": created_at,
        "updated_at": created_at,
        "input": input_payload,
        # Initialize a structured clarification template for "understand first, then generate".
        "clarification": {
            "questions": build_default_clarification_questions(payload),
            "submitted": False,
        },
        "outline": None,
        "error": None,
        "runtime": {"generation_attempts": 0, "last_started_at": None, "last_finished_at": None},
    }
    persist_task(task)
    logger.info("Task created task_id=%s status=%s", task_id, task["status"])
    return CreateTaskResponse(task_id=task_id, status=TaskStatus.clarifying, created_at=created_at)


@router.get("/{task_id:uuid}")
def get_task(task_id: UUID) -> dict[str, Any]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    return task_snapshot(get_task_or_404(task_id_str))


@router.get("", response_model=ListTasksResponse)
def list_tasks(status_filter: TaskStatus | None = None, limit: int = 20) -> ListTasksResponse:
    limit = max(1, min(limit, 200))
    if USE_DB_STORE:
        tasks = db_list_tasks(limit=limit)
    else:
        tasks = list(TASK_STORE.values())
        tasks.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        tasks = tasks[:limit]

    if status_filter is not None:
        tasks = [task for task in tasks if task.get("status") == status_filter.value]
    snapshots = [task_snapshot(task) for task in tasks]
    return ListTasksResponse(tasks=snapshots, total=len(snapshots))


@router.get("/export", response_model=ListTasksResponse)
def export_tasks_for_evaluation(
    status_filter: TaskStatus | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    limit: int = 100,
) -> ListTasksResponse:
    limit = max(1, min(limit, 500))
    if USE_DB_STORE:
        tasks = db_list_tasks(limit=limit)
    else:
        tasks = list(TASK_STORE.values())
        tasks.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        tasks = tasks[:limit]

    def _in_window(value: str) -> bool:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return False
        if updated_after:
            try:
                if dt < datetime.fromisoformat(updated_after):
                    return False
            except ValueError:
                pass
        if updated_before:
            try:
                if dt > datetime.fromisoformat(updated_before):
                    return False
            except ValueError:
                pass
        return True

    filtered: list[dict[str, Any]] = []
    for task in tasks:
        status_value = str(task.get("status") or "")
        if status_filter is not None and status_value != status_filter.value:
            continue
        updated_at = str(task.get("updated_at") or "")
        if updated_after or updated_before:
            if not _in_window(updated_at):
                continue
        filtered.append(task)
    snapshots = [task_snapshot(task) for task in filtered[:limit]]
    return ListTasksResponse(tasks=snapshots, total=len(snapshots))


@router.patch("/{task_id:uuid}/clarification")
def patch_clarification(task_id: UUID, payload: PatchClarificationRequest) -> dict[str, Any]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
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
    submitted = bool(task["clarification"].get("submitted"))
    task["status"] = TaskStatus.pending.value if submitted else TaskStatus.clarifying.value

    task["updated_at"] = now_iso()
    persist_task(task)
    logger.info("Clarification updated task_id=%s submitted=%s", task_id_str, task["clarification"]["submitted"])
    return task_snapshot(task)


def complete_generation(task_id: str) -> None:
    try:
        task = fetch_task(task_id)
        if task is None:
            return

        # Special marker to let evaluation scripts reliably cover failed status flow.
        if should_force_fail(task["input"]["topic"]):
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

        with ThreadPoolExecutor(max_workers=1) as local_executor:
            future = local_executor.submit(
                generate_outline_with_research,
                topic=task["input"]["topic"],
                retrieval_depth=task["input"]["retrieval_depth"],
                clarification=task.get("clarification"),
                raw_notes=task["input"].get("raw_notes"),
                source_type=task["input"].get("source_type", "short_topic"),
                document_text=task["input"].get("document_text"),
                document_title=task["input"].get("document_title"),
                document_profile=task["input"].get("document_profile"),
            )
            try:
                task["outline"] = future.result(timeout=max(1, settings.generation_hard_timeout_seconds))
            except FuturesTimeoutError as timeout_exc:
                raise GenerationTimeoutError("hard timeout exceeded") from timeout_exc
        runtime = task.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
        runtime["last_finished_at"] = now_iso()
        task["runtime"] = runtime
        task["status"] = TaskStatus.done.value
        task["error"] = None
        task["updated_at"] = now_iso()
        persist_task(task)
        logger.info("Task completed task_id=%s status=%s", task_id, task["status"])
    except Exception as exc:
        logger.exception("Task generation crashed task_id=%s", task_id)
        task = fetch_task(task_id)
        if task is not None:
            runtime = task.get("runtime", {})
            if not isinstance(runtime, dict):
                runtime = {}
            attempts = int(runtime.get("generation_attempts", 1))
            max_retries = max(0, settings.generation_max_retries)
            runtime["last_finished_at"] = now_iso()
            task["runtime"] = runtime
            error_code, error_message, error_details = classify_generation_exception(exc)
            if attempts < max_retries:
                # Auto-retry in background with bounded attempts; avoid getting stuck in pending.
                next_attempt = attempts + 1
                runtime["generation_attempts"] = next_attempt
                runtime["last_started_at"] = now_iso()
                task["status"] = TaskStatus.generating.value
                task["error"] = {
                    "code": error_code,
                    "message": f"{error_message} Auto retry scheduled.",
                    "details": {
                        **error_details,
                        "attempts": attempts,
                        "next_attempt": next_attempt,
                        "max_retries": max_retries,
                    },
                }
                task["runtime"] = runtime
                task["updated_at"] = now_iso()
                persist_task(task)
                enqueue_generation(task_id)
                return
            else:
                task["status"] = TaskStatus.failed.value
                task["error"] = {
                    "code": error_code,
                    "message": error_message,
                    "details": {**error_details, "retryable": False, "attempts": attempts, "max_retries": max_retries},
                }
            task["updated_at"] = now_iso()
            persist_task(task)


@router.post("/{task_id:uuid}/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_task(task_id: UUID, payload: GenerateTaskRequest | None = None) -> GenerateResponse:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] not in (TaskStatus.pending.value, TaskStatus.clarifying.value):
        if task["status"] == TaskStatus.generating.value:
            return GenerateResponse(task_id=task_id_str, status=TaskStatus.generating, accepted=True, idempotent=True)
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Task cannot be generated in current state.",
            {"status": task["status"]},
        )
    if not bool(task["clarification"].get("submitted")):
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Clarification must be submitted before generation.",
        )

    idempotency_key = (payload.idempotency_key if payload else None) or ""
    runtime = task.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}

    task["status"] = TaskStatus.generating.value
    task["runtime"] = {
        "generation_attempts": int(runtime.get("generation_attempts", 0)) + 1,
        "last_started_at": now_iso(),
        "last_idempotency_key": idempotency_key or None,
        "last_finished_at": runtime.get("last_finished_at"),
    }
    task["updated_at"] = now_iso()
    persist_task(task)
    logger.info("Task accepted task_id=%s status=%s", task_id_str, task["status"])
    # Return quickly and finish generation in background to match async contract.
    enqueue_generation(task_id_str)
    return GenerateResponse(task_id=task_id_str, status=TaskStatus.generating, accepted=True, idempotent=False)


def recover_inflight_generations(limit: int = 100) -> int:
    """Resubmit inflight tasks on process restart."""
    inflight = fetch_tasks_by_status(TaskStatus.generating, limit=limit)
    recovered = 0
    stale_seconds = max(1, settings.recovery_stale_generating_seconds)
    now = datetime.now(timezone.utc)
    for task in inflight:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        updated_at = str(task.get("updated_at") or "")
        is_stale = True
        if updated_at:
            try:
                delta = now - datetime.fromisoformat(updated_at)
                is_stale = delta.total_seconds() >= stale_seconds
            except ValueError:
                is_stale = True

        if is_stale:
            task["status"] = TaskStatus.pending.value
            task["updated_at"] = now_iso()
            task["error"] = {
                "code": "INTERNAL_ERROR",
                "message": "Recovered stale generating task, set back to pending.",
                "details": {"recovered": True},
            }
            persist_task(task)
        enqueue_generation(task_id)
        recovered += 1
    if recovered:
        logger.warning("Recovered inflight generation tasks count=%s", recovered)
    return recovered


@router.post("/{task_id:uuid}/retry", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_failed_task(task_id: UUID) -> GenerateResponse:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] != TaskStatus.failed.value:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Only failed tasks can be retried.",
            {"status": task["status"]},
        )

    task["status"] = TaskStatus.pending.value
    task["updated_at"] = now_iso()
    persist_task(task)
    return generate_task(task_id=UUID(task_id_str), payload=GenerateTaskRequest(idempotency_key=f"retry-{now_iso()}"))
