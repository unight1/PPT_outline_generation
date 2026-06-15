from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.task_store import get_task as db_get_task
from app.task_store import list_tasks as db_list_tasks
from app.task_store import list_tasks_by_status as db_list_tasks_by_status
from app.task_store import delete_task as db_delete_task
from app.task_store import save_task as db_save_task
from app.task_store import store_available
from app.services.clarification import build_clarification_questions, build_fallback_clarification_questions
from app.services.document_llm import enrich_document_profile, merge_enrichment_into_profile
from app.services.document_processing import build_document_profile
from app.services.generation import should_force_fail
from app.services.pptx_export import export_outline_to_pptx
from app.services.orchestration import generate_outline_with_research
from app.services.page_generation import SlideWorkflowError, generate_pages_from_skeleton
from app.services.skeleton import generate_outline_skeleton
from app.services.task_documents import (
    DocumentUploadError,
    filename_for_document_title,
    public_attachment,
    save_task_document,
    save_task_document_text,
)

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


class SourceQuality(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


WorkflowPhase = Literal[
    "idle",
    "document_analysis",
    "skeleton_llm",
    "skeleton_ready",
    "retrieving_page",
    "llm_page",
    "assembling",
    "saving",
    "regenerating_slide",
    "done",
    "failed",
]


class Problem(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CreateTaskRequest(BaseModel):
    topic: str = Field(min_length=1)
    source_type: Literal["short_topic", "long_document"] = "short_topic"
    audience: str | None = None
    duration_minutes: int = Field(default=15, ge=5, le=120)
    target_pages: int | None = Field(default=None, ge=3, le=30)
    target_pages_min: int | None = Field(default=None, ge=3, le=30)
    target_pages_max: int | None = Field(default=None, ge=3, le=30)
    desired_chapters: str | None = None
    language: str = "zh"
    retrieval_depth: RetrievalDepth = RetrievalDepth.l1
    raw_notes: str | None = None
    document_text: str | None = None
    document_title: str | None = None

    @model_validator(mode="after")
    def validate_long_document_input(self) -> "CreateTaskRequest":
        if self.source_type == "long_document" and not (self.document_text or "").strip():
            raise ValueError("document_text is required when source_type=long_document")
        if (
            self.target_pages_min is not None
            and self.target_pages_max is not None
            and self.target_pages_min > self.target_pages_max
        ):
            raise ValueError("target_pages_min must be less than or equal to target_pages_max")
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


class Progress(BaseModel):
    phase: WorkflowPhase
    current: int | None = None
    total: int | None = None
    message: str = ""
    percent: int | None = None


class OutlineSkeletonSlide(BaseModel):
    slide_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    intent: str | None = None
    user_notes: str | None = None
    chapter_id: str | None = None


class OutlineChapter(BaseModel):
    chapter_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    slide_ids: list[str] = Field(default_factory=list)


class PatchSkeletonRequest(BaseModel):
    slides: list[OutlineSkeletonSlide] = Field(min_length=1)
    chapters: list[OutlineChapter] | None = None

    @model_validator(mode="after")
    def validate_unique_slide_ids(self) -> "PatchSkeletonRequest":
        slide_ids = [slide.slide_id for slide in self.slides]
        if len(slide_ids) != len(set(slide_ids)):
            raise ValueError("slide_id must be unique within outline_skeleton")
        if self.chapters is not None:
            valid_slide_ids = set(slide_ids)
            chapter_ids = [chapter.chapter_id for chapter in self.chapters]
            if len(chapter_ids) != len(set(chapter_ids)):
                raise ValueError("chapter_id must be unique within chapters")
            assigned_slide_ids: list[str] = []
            for chapter in self.chapters:
                for slide_id in chapter.slide_ids:
                    if slide_id not in valid_slide_ids:
                        raise ValueError("chapter slide_ids must reference existing slides")
                    assigned_slide_ids.append(slide_id)
            if len(assigned_slide_ids) != len(set(assigned_slide_ids)):
                raise ValueError("each slide can belong to at most one chapter")
        return self


class GenerateSlidesRequest(BaseModel):
    idempotency_key: str | None = None
    concurrency: int | None = Field(default=None, ge=1, le=3)
    force_refresh: bool = False
    retrieval_depth: RetrievalDepth | None = None
    tavily_enabled: bool | None = None
    retrieval_policy: "RetrievalPolicyRequest | None" = None


class RetrievalPolicyRequest(BaseModel):
    retrieval_depth: RetrievalDepth | None = None
    tavily_enabled: bool | None = None
    prefer_user_doc: bool | None = None
    source_quality: SourceQuality | None = None
    force_refresh: bool | None = None
    enable_fallback_deepen: bool | None = None


class OutlineBullet(BaseModel):
    bullet_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class OutlineSlide(BaseModel):
    slide_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    bullets: list[OutlineBullet] = Field(default_factory=list)
    speaker_notes: str | None = None


class EvidenceItem(BaseModel):
    evidence_id: str = Field(min_length=1)
    snippet: str = ""
    source_id: str = "unknown"
    locator: str = ""
    score: float | None = None
    confidence: float | None = None


class PatchOutlineRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    slides: list[OutlineSlide] | None = None
    evidence_catalog: list[EvidenceItem] | None = None

    @model_validator(mode="after")
    def validate_has_update(self) -> "PatchOutlineRequest":
        if self.title is None and self.slides is None and self.evidence_catalog is None:
            raise ValueError("At least one of title, slides, evidence_catalog is required")
        if self.slides is not None:
            slide_ids = [slide.slide_id for slide in self.slides]
            if len(slide_ids) != len(set(slide_ids)):
                raise ValueError("slide_id must be unique within slides")
        return self


class ListTasksResponse(BaseModel):
    tasks: list[dict[str, Any]]
    total: int


class GenerateTaskRequest(BaseModel):
    idempotency_key: str | None = None


class RegenerateSlideRequest(BaseModel):
    user_instruction: str | None = None


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: Literal["pending", "ready", "failed"]
    chunk_count: int | None = None


TASK_STORE: dict[str, dict[str, Any]] = {}
# Prefer MySQL when configured; keep in-memory fallback for local demos/tests.
USE_DB_STORE = store_available()
GENERATION_EXECUTOR = ThreadPoolExecutor(max_workers=settings.generation_worker_max_workers)


class GenerationTimeoutError(RuntimeError):
    pass


def build_progress(
    phase: WorkflowPhase,
    message: str,
    current: int | None = None,
    total: int | None = None,
    percent: int | None = None,
) -> dict[str, Any]:
    return Progress(
        phase=phase,
        current=current,
        total=total,
        message=message,
        percent=percent,
    ).model_dump()


def update_task_progress(
    task: dict[str, Any],
    phase: WorkflowPhase,
    message: str,
    current: int | None = None,
    total: int | None = None,
    percent: int | None = None,
) -> None:
    task["progress"] = build_progress(
        phase=phase,
        message=message,
        current=current,
        total=total,
        percent=percent,
    )


def build_default_clarification_questions(payload: CreateTaskRequest) -> list[dict[str, Any]]:
    return build_fallback_clarification_questions(payload)


def _source_quality_default() -> str:
    value = str(settings.retrieval_default_source_quality or "medium").lower()
    return value if value in {"low", "medium", "high"} else "medium"


def _normalize_retrieval_depth(value: Any) -> str:
    if isinstance(value, RetrievalDepth):
        return value.value
    text = str(value or "L1").upper()
    if text.endswith(".L0") or text.endswith("L0"):
        return "L0"
    if text.endswith(".L2") or text.endswith("L2"):
        return "L2"
    return "L1"


def _default_retrieval_policy(task: dict[str, Any]) -> dict[str, Any]:
    input_payload = task.get("input") if isinstance(task.get("input"), dict) else {}
    return {
        "retrieval_depth": _normalize_retrieval_depth(input_payload.get("retrieval_depth")),
        "tavily_enabled": bool(settings.retrieval_tavily_enabled),
        "prefer_user_doc": str(input_payload.get("source_type") or "") == "long_document",
        "source_quality": _source_quality_default(),
        "force_refresh": False,
        "enable_fallback_deepen": bool(settings.retrieval_enable_fallback_deepen),
    }


def _policy_payload(payload: GenerateSlidesRequest | None) -> dict[str, Any]:
    if payload is None:
        return {}
    values: dict[str, Any] = {}
    # v1.0 top-level compatibility first; nested retrieval_policy wins below.
    if payload.retrieval_depth is not None:
        values["retrieval_depth"] = payload.retrieval_depth.value
    if payload.tavily_enabled is not None:
        values["tavily_enabled"] = payload.tavily_enabled
    if payload.force_refresh:
        values["force_refresh"] = True
    if payload.retrieval_policy is not None:
        for key, value in payload.retrieval_policy.model_dump(exclude_none=True).items():
            values[key] = value.value if isinstance(value, Enum) else value
    return values


def merge_retrieval_policy(task: dict[str, Any], payload: GenerateSlidesRequest | None = None) -> dict[str, Any]:
    runtime = task.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    existing = runtime.get("retrieval_policy")
    if not isinstance(existing, dict):
        existing = {}
    merged = {
        **_default_retrieval_policy(task),
        **{key: value for key, value in existing.items() if value is not None},
        **_policy_payload(payload),
    }
    merged["retrieval_depth"] = _normalize_retrieval_depth(merged.get("retrieval_depth"))
    merged["source_quality"] = str(merged.get("source_quality") or _source_quality_default()).lower()
    if merged["source_quality"] not in {"low", "medium", "high"}:
        merged["source_quality"] = _source_quality_default()
    for key in ("tavily_enabled", "prefer_user_doc", "force_refresh", "enable_fallback_deepen"):
        merged[key] = bool(merged.get(key))
    return merged


def persist_task(task: dict[str, Any]) -> None:
    if USE_DB_STORE:
        db_save_task(task)
        return
    TASK_STORE[task["task_id"]] = task


def _task_matches_search(task: dict[str, Any], keyword: str) -> bool:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    topic = str(input_data.get("topic") or "").lower()
    if keyword in topic:
        return True
    title = str(input_data.get("document_title") or "").lower()
    if keyword in title:
        return True
    outline = task.get("outline")
    if isinstance(outline, dict):
        outline_title = str(outline.get("title") or "").lower()
        if keyword in outline_title:
            return True
    return False


def _clarification_payload_from_task(task: dict[str, Any]) -> CreateTaskRequest:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    duration = input_data.get("duration_minutes")
    return CreateTaskRequest(
        topic=str(input_data.get("topic") or "主题"),
        source_type=input_data.get("source_type") or "short_topic",
        audience=input_data.get("audience"),
        duration_minutes=int(duration) if isinstance(duration, int) else 15,
        target_pages_min=input_data.get("target_pages_min"),
        target_pages_max=input_data.get("target_pages_max"),
        desired_chapters=input_data.get("desired_chapters"),
        language=str(input_data.get("language") or "zh"),
        retrieval_depth=RetrievalDepth(_normalize_retrieval_depth(input_data.get("retrieval_depth"))),
        raw_notes=input_data.get("raw_notes"),
        document_text=input_data.get("document_text"),
        document_title=input_data.get("document_title"),
    )


def _refresh_clarification_questions(task: dict[str, Any]) -> None:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    profile = input_data.get("document_profile")
    payload = _clarification_payload_from_task(task)
    task["clarification"] = {
        "questions": build_clarification_questions(
            payload,
            document_profile=profile if isinstance(profile, dict) else None,
            fallback_builder=build_default_clarification_questions,
        ),
        "submitted": False,
    }
    update_task_progress(task, "idle", "文档摘要已完成，请回答澄清问题。")


def _finish_document_analysis(task: dict[str, Any], *, status: str) -> None:
    runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    runtime["document_analysis_status"] = status
    task["runtime"] = runtime
    _refresh_clarification_questions(task)
    task["updated_at"] = now_iso()
    persist_task(task)


def _enrich_document_profile_background(task_id: str) -> None:
    try:
        task = fetch_task(task_id)
        if task is None:
            return
        input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
        document_text = str(input_data.get("document_text") or "")
        if not document_text.strip():
            _finish_document_analysis(task, status="done")
            return

        topic = str(input_data.get("topic") or "")
        document_title = str(input_data.get("document_title") or "")
        enrichment = enrich_document_profile(
            document_text=document_text,
            topic=topic,
            document_title=document_title,
        )
        rule_profile = input_data.get("document_profile")
        merged = merge_enrichment_into_profile(rule_profile, enrichment)
        input_data["document_profile"] = merged
        task["input"] = input_data
        _finish_document_analysis(task, status="done")
        logger.info("Document profile enriched task_id=%s", task_id)
    except Exception:
        logger.exception("Document profile enrichment failed task_id=%s", task_id)
        task = fetch_task(task_id)
        if task is not None:
            _finish_document_analysis(task, status="failed")


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


def delete_task(task_id: str) -> bool:
    if USE_DB_STORE:
        if db_get_task(task_id) is None:
            return False
        return db_delete_task(task_id)
    if task_id in TASK_STORE:
        del TASK_STORE[task_id]
        return True
    return False


def enqueue_generation(task_id: str) -> Future[None]:
    return GENERATION_EXECUTOR.submit(complete_generation, task_id)


def enqueue_skeleton_generation(task_id: str) -> Future[None]:
    return GENERATION_EXECUTOR.submit(complete_skeleton_generation, task_id)


def enqueue_slide_generation(task_id: str) -> Future[None]:
    return GENERATION_EXECUTOR.submit(complete_slide_generation, task_id)


def enqueue_slides_generation(task_id: str, concurrency: int = 2) -> Future[None]:
    return GENERATION_EXECUTOR.submit(complete_slide_generation, task_id, concurrency)


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


def classify_slide_generation_exception(
    exc: Exception,
    *,
    phase: str | None = None,
    slide_id: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    if isinstance(exc, SlideWorkflowError):
        details: dict[str, Any] = {
            "retryable": exc.retryable,
            "phase": exc.phase or phase,
        }
        if exc.slide_id or slide_id:
            details["slide_id"] = exc.slide_id or slide_id
        if exc.reason:
            details["reason"] = exc.reason
        return exc.code, exc.message, details

    if isinstance(exc, GenerationTimeoutError):
        return (
            "TIMEOUT",
            "按页生成超时。",
            {"retryable": True, "phase": phase or "llm_page", "slide_id": slide_id, "reason": "hard-timeout"},
        )

    message = str(exc)
    lowered = message.lower()
    if "timeout" in lowered:
        return (
            "TIMEOUT",
            "按页生成超时，请稍后重试。",
            {"retryable": True, "phase": phase or "llm_page", "slide_id": slide_id, "reason": "upstream-timeout"},
        )
    if "tavily" in lowered:
        return (
            "TAVILY_ERROR",
            "网络检索失败，请检查 Tavily 或关闭联网检索。",
            {"retryable": True, "phase": phase or "retrieving_page", "slide_id": slide_id, "reason": message},
        )
    if any(token in lowered for token in ("chroma", "embedding", "retriev", "index")):
        return (
            "RETRIEVAL_ERROR",
            "本地检索失败，请检查文档索引。",
            {"retryable": True, "phase": phase or "retrieving_page", "slide_id": slide_id, "reason": message},
        )
    if any(token in lowered for token in ("openai", "llm", "json", "api_key", "model")):
        return (
            "LLM_ERROR",
            "模型生成失败，请稍后重试。",
            {"retryable": True, "phase": phase or "llm_page", "slide_id": slide_id, "reason": message},
        )
    return (
        "INTERNAL_ERROR",
        "按页生成失败。",
        {"retryable": True, "phase": phase, "slide_id": slide_id, "reason": message},
    )


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
    input_payload = dict(task.get("input") if isinstance(task.get("input"), dict) else {})
    attachments = input_payload.get("attachments")
    if isinstance(attachments, list):
        input_payload["attachments"] = [
            public_attachment(item)
            for item in attachments
            if isinstance(item, dict)
        ]
    else:
        input_payload["attachments"] = []
    skeleton_chapters = task.get("outline_skeleton_chapters")
    if not isinstance(skeleton_chapters, list) or not skeleton_chapters:
        skeleton_chapters = _rebuild_skeleton_chapters_from_slides(task.get("outline_skeleton"))
    # Keep v0 fields while exposing the v1 workflow fields for new clients.
    return {
        "task_id": task["task_id"],
        "schema_version": task.get("schema_version", settings.task_schema_version),
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "clarification": task["clarification"],
        "outline_skeleton": task.get("outline_skeleton"),
        "outline_skeleton_chapters": skeleton_chapters,
        "outline": task.get("outline"),
        "progress": task.get("progress"),
        "error": task.get("error"),
        "input": input_payload,
        "runtime": task.get("runtime"),
    }


def _rebuild_skeleton_chapters_from_slides(skeleton: Any) -> list[dict[str, Any]]:
    if not isinstance(skeleton, list) or not skeleton:
        return []
    grouped: dict[str, list[str]] = {}
    title_by_chapter: dict[str, str] = {}
    for slide in skeleton:
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slide_id") or "")
        chapter_id = str(slide.get("chapter_id") or "")
        if not slide_id or not chapter_id:
            continue
        grouped.setdefault(chapter_id, []).append(slide_id)
        title_by_chapter.setdefault(chapter_id, str(slide.get("title") or chapter_id))
    return [
        {
            "chapter_id": chapter_id,
            "title": f"章节：{title_by_chapter.get(chapter_id, chapter_id)}",
            "slide_ids": slide_ids,
        }
        for chapter_id, slide_ids in grouped.items()
    ]


def _rebuild_page_evidence_map(outline: dict[str, Any]) -> None:
    catalog = outline.get("evidence_catalog", [])
    if not isinstance(catalog, list):
        catalog = []
    ev_lookup = {
        str(item.get("evidence_id")): item
        for item in catalog
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }
    valid_ids = set(ev_lookup)
    page_evidence_map: list[dict[str, Any]] = []
    slides = outline.get("slides", [])
    if not isinstance(slides, list):
        outline["page_evidence_map"] = page_evidence_map
        return

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        ev_to_bullets: dict[str, list[str]] = {}
        bullets = slide.get("bullets", [])
        if isinstance(bullets, list):
            for bullet in bullets:
                if not isinstance(bullet, dict):
                    continue
                raw_ids = bullet.get("evidence_ids", [])
                if not isinstance(raw_ids, list):
                    raw_ids = []
                cleaned_ids = [str(eid) for eid in raw_ids if str(eid) in valid_ids]
                bullet["evidence_ids"] = cleaned_ids
                bullet_id = str(bullet.get("bullet_id") or "")
                for eid in cleaned_ids:
                    ev_to_bullets.setdefault(eid, []).append(bullet_id)
        evidence_trace: list[dict[str, Any]] = []
        for eid, bullet_ids in ev_to_bullets.items():
            entry = dict(ev_lookup[eid])
            entry["bullet_ids"] = bullet_ids
            evidence_trace.append(entry)
        page_evidence_map.append(
            {
                "slide_id": str(slide.get("slide_id") or ""),
                "slide_title": str(slide.get("title") or ""),
                "evidence_trace": evidence_trace,
            }
        )
    outline["page_evidence_map"] = page_evidence_map


@router.post("", response_model=CreateTaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: CreateTaskRequest) -> CreateTaskResponse:
    task_id = str(uuid4())
    created_at = now_iso()
    input_payload = payload.model_dump()
    input_payload["attachments"] = []
    if payload.source_type == "long_document":
        input_payload["document_profile"] = build_document_profile(payload.document_text)
        try:
            attachment = save_task_document_text(
                task_id,
                str(payload.document_text or ""),
                filename=filename_for_document_title(payload.document_title),
            )
            input_payload["attachments"] = [public_attachment(attachment)]
        except DocumentUploadError as exc:
            raise build_error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.code, exc.message, exc.details) from exc
    else:
        input_payload["document_profile"] = None

    doc_analysis_status = None
    if payload.source_type == "long_document" and (payload.document_text or "").strip():
        if settings.use_real_llm and settings.openai_api_key:
            doc_analysis_status = "running"
        else:
            doc_analysis_status = "done"

    runtime = {
        "workflow": None,
        "generation_attempts": 0,
        "last_started_at": None,
        "last_finished_at": None,
        "document_analysis_status": doc_analysis_status,
    }
    task = {
        "task_id": task_id,
        "schema_version": settings.task_schema_version,
        "status": TaskStatus.clarifying.value,
        "created_at": created_at,
        "updated_at": created_at,
        "input": input_payload,
        "clarification": {"questions": [], "submitted": False},
        "outline_skeleton": None,
        "outline": None,
        "progress": None,
        "error": None,
        "runtime": runtime,
    }
    task["runtime"]["retrieval_policy"] = _default_retrieval_policy(task)
    if doc_analysis_status == "running":
        update_task_progress(
            task,
            "document_analysis",
            "正在分析长文档并提炼摘要，完成后将生成澄清问题。",
        )
    else:
        _refresh_clarification_questions(task)
        if not task.get("progress"):
            update_task_progress(task, "idle", "任务已创建，等待提交澄清。")
    persist_task(task)
    logger.info("Task created task_id=%s status=%s", task_id, task["status"])

    if doc_analysis_status == "running":
        GENERATION_EXECUTOR.submit(_enrich_document_profile_background, task_id)

    return CreateTaskResponse(task_id=task_id, status=TaskStatus.clarifying, created_at=created_at)


@router.get("/{task_id:uuid}")
def get_task(task_id: UUID) -> dict[str, Any]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    return task_snapshot(get_task_or_404(task_id_str))


@router.post("/{task_id:uuid}/documents/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_task_document(task_id: UUID, file: UploadFile = File(...)) -> DocumentUploadResponse:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] == TaskStatus.generating.value:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Cannot upload documents while generation is running.",
            {"status": task["status"]},
        )

    content = await file.read()
    try:
        attachment = save_task_document(task_id_str, file.filename or "upload.txt", content)
    except DocumentUploadError as exc:
        raise build_error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.code, exc.message, exc.details) from exc
    except Exception as exc:
        logger.exception("Document upload failed task_id=%s filename=%s", task_id_str, file.filename)
        attachment = {
            "document_id": f"doc_failed_{uuid4().hex[:8]}",
            "filename": file.filename or "upload.txt",
            "status": "failed",
            "chunk_count": None,
            "error": str(exc),
        }

    input_payload = task.get("input")
    if not isinstance(input_payload, dict):
        input_payload = {}
    attachments = input_payload.get("attachments")
    if not isinstance(attachments, list):
        attachments = []
    attachments.append(attachment)
    input_payload["attachments"] = attachments
    task["input"] = input_payload
    task["updated_at"] = now_iso()
    persist_task(task)
    return DocumentUploadResponse(**public_attachment(attachment))


@router.get("", response_model=ListTasksResponse)
def list_tasks(
    status_filter: TaskStatus | None = None,
    search: str | None = None,
    limit: int = 20,
) -> ListTasksResponse:
    limit = max(1, min(limit, 200))
    if USE_DB_STORE:
        tasks_list = db_list_tasks(limit=500)
    else:
        tasks_list = list(TASK_STORE.values())
        tasks_list.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)

    if status_filter is not None:
        tasks_list = [t for t in tasks_list if t.get("status") == status_filter.value]
    if search and search.strip():
        keyword = search.strip().lower()
        tasks_list = [
            t for t in tasks_list
            if _task_matches_search(t, keyword)
        ]
    tasks_list = tasks_list[:limit]
    snapshots = [task_snapshot(task) for task in tasks_list]
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


@router.post("/{task_id:uuid}/skeleton/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_skeleton(task_id: UUID, payload: GenerateTaskRequest | None = None) -> GenerateResponse:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] == TaskStatus.generating.value:
        progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
        if progress.get("phase") == "skeleton_llm":
            return GenerateResponse(task_id=task_id_str, status=TaskStatus.generating, accepted=True, idempotent=True)
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Task is already generating another workflow.",
            {"status": task["status"], "phase": progress.get("phase")},
        )
    if task["status"] not in (TaskStatus.pending.value, TaskStatus.clarifying.value):
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Skeleton cannot be generated in current state.",
            {"status": task["status"]},
        )
    if not bool(task["clarification"].get("submitted")):
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Clarification must be submitted before skeleton generation.",
        )

    runtime = task.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    idempotency_key = (payload.idempotency_key if payload else None) or ""
    task["status"] = TaskStatus.generating.value
    task["error"] = None
    task["runtime"] = {
        **runtime,
        "workflow": "skeleton",
        "last_started_at": now_iso(),
        "last_idempotency_key": idempotency_key or None,
    }
    update_task_progress(task, "skeleton_llm", "正在生成可编辑骨架。")
    task["updated_at"] = now_iso()
    persist_task(task)
    enqueue_skeleton_generation(task_id_str)
    return GenerateResponse(task_id=task_id_str, status=TaskStatus.generating, accepted=True, idempotent=False)


@router.patch("/{task_id:uuid}/skeleton")
def patch_skeleton(task_id: UUID, payload: PatchSkeletonRequest) -> dict[str, Any]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] == TaskStatus.generating.value:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Cannot update skeleton while generation is running.",
            {"status": task["status"]},
        )
    if task["status"] not in (TaskStatus.pending.value, TaskStatus.clarifying.value, TaskStatus.failed.value):
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Skeleton cannot be updated in current state.",
            {"status": task["status"]},
        )
    if not task.get("outline_skeleton"):
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "Skeleton has not been generated yet.")

    old_chapter_by_slide: dict[str, str] = {}
    old_skeleton = task.get("outline_skeleton")
    if isinstance(old_skeleton, list):
        for item in old_skeleton:
            if not isinstance(item, dict):
                continue
            slide_id = str(item.get("slide_id") or "")
            chapter_id = item.get("chapter_id")
            if slide_id and chapter_id:
                old_chapter_by_slide[slide_id] = str(chapter_id)
    slides = []
    for slide in payload.slides:
        item = slide.model_dump()
        if not item.get("chapter_id"):
            item["chapter_id"] = old_chapter_by_slide.get(item["slide_id"])
        slides.append(item)
    task["outline_skeleton"] = slides
    if payload.chapters is not None:
        chapters = [chapter.model_dump() for chapter in payload.chapters]
        chapter_by_slide: dict[str, str] = {}
        for chapter in chapters:
            for slide_id in chapter.get("slide_ids", []):
                chapter_by_slide[str(slide_id)] = str(chapter["chapter_id"])
        for slide in slides:
            slide["chapter_id"] = chapter_by_slide.get(str(slide["slide_id"]))
        task["outline_skeleton_chapters"] = chapters
    else:
        chapters = task.get("outline_skeleton_chapters")
        if isinstance(chapters, list):
            valid_slide_ids = {str(slide["slide_id"]) for slide in slides}
            task["outline_skeleton_chapters"] = [
                {
                    **chapter,
                    "slide_ids": [
                        str(slide_id)
                        for slide_id in (chapter.get("slide_ids") or [])
                        if str(slide_id) in valid_slide_ids
                    ],
                }
                for chapter in chapters
                if isinstance(chapter, dict)
            ]
    if task["status"] == TaskStatus.failed.value:
        task["status"] = TaskStatus.pending.value
        task["error"] = None
    update_task_progress(
        task,
        "skeleton_ready",
        "骨架已更新，请确认后生成完整大纲。",
        total=len(slides),
    )
    task["updated_at"] = now_iso()
    persist_task(task)
    return task_snapshot(task)


@router.patch("/{task_id:uuid}/outline")
def patch_outline(task_id: UUID, payload: PatchOutlineRequest) -> dict[str, Any]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] == TaskStatus.generating.value:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Cannot update outline while generation is running.",
            {"status": task["status"]},
        )
    if task["status"] != TaskStatus.done.value:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Outline can only be updated after generation is done.",
            {"status": task["status"]},
        )
    outline = task.get("outline")
    if not isinstance(outline, dict):
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "Outline has not been generated yet.")

    if payload.title is not None:
        outline["title"] = payload.title

    if payload.evidence_catalog is not None:
        outline["evidence_catalog"] = [item.model_dump() for item in payload.evidence_catalog]

    if payload.slides is not None:
        existing_slides = outline.get("slides", [])
        if not isinstance(existing_slides, list):
            existing_slides = []
        incoming = {slide.slide_id: slide.model_dump() for slide in payload.slides}
        known_ids = {
            str(slide.get("slide_id"))
            for slide in existing_slides
            if isinstance(slide, dict) and str(slide.get("slide_id") or "").strip()
        }
        unknown_ids = sorted(set(incoming) - known_ids)
        if unknown_ids:
            raise build_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDATION_ERROR",
                "slides contains unknown slide_id.",
                {"slide_ids": unknown_ids},
            )
        outline["slides"] = [
            incoming.get(str(slide.get("slide_id")), slide) if isinstance(slide, dict) else slide
            for slide in existing_slides
        ]

    _rebuild_page_evidence_map(outline)
    task["outline"] = outline
    update_task_progress(task, "done", "大纲修改已保存。", percent=100)
    task["updated_at"] = now_iso()
    persist_task(task)
    return task_snapshot(task)


@router.post("/{task_id:uuid}/slides/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_slides(task_id: UUID, payload: GenerateSlidesRequest | None = None) -> GenerateResponse:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    if task["status"] == TaskStatus.generating.value:
        progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
        if progress.get("phase") in ("retrieving_page", "llm_page", "assembling", "saving"):
            return GenerateResponse(task_id=task_id_str, status=TaskStatus.generating, accepted=True, idempotent=True)
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Task is already generating another workflow.",
            {"status": task["status"], "phase": progress.get("phase")},
        )
    allowed_statuses = (TaskStatus.pending.value, TaskStatus.failed.value)
    if task["status"] not in allowed_statuses:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Slides cannot be generated in current state.",
            {"status": task["status"]},
        )
    if not bool(task["clarification"].get("submitted")):
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "Clarification must be submitted first.")
    skeleton = task.get("outline_skeleton")
    if not isinstance(skeleton, list) or not skeleton:
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "Skeleton must be generated before slides.")

    runtime = task.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    idempotency_key = (payload.idempotency_key if payload else None) or ""
    was_failed = task["status"] == TaskStatus.failed.value
    task["status"] = TaskStatus.generating.value
    task["error"] = None
    if was_failed and task.get("outline"):
        task["outline"] = None
    concurrency = payload.concurrency if payload and payload.concurrency is not None else 2
    retrieval_policy = merge_retrieval_policy(task, payload)
    task["input"]["retrieval_depth"] = retrieval_policy["retrieval_depth"]
    task["runtime"] = {
        **runtime,
        "workflow": "slides",
        "last_started_at": now_iso(),
        "last_idempotency_key": idempotency_key or None,
        "concurrency": concurrency,
        "retrieval_policy": retrieval_policy,
        # Compatibility for older code/tests that still inspect generation_* runtime keys.
        "generation_retrieval_depth": retrieval_policy["retrieval_depth"],
        "generation_tavily_enabled": retrieval_policy["tavily_enabled"],
        "force_refresh_retrieval": retrieval_policy["force_refresh"],
    }
    update_task_progress(task, "retrieving_page", "正在准备按页生成。", current=0, total=len(skeleton), percent=0)
    task["updated_at"] = now_iso()
    persist_task(task)
    enqueue_slides_generation(task_id_str, concurrency)
    return GenerateResponse(task_id=task_id_str, status=TaskStatus.generating, accepted=True, idempotent=False)


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

    runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    questions = task.get("clarification", {}).get("questions") if isinstance(task.get("clarification"), dict) else []
    if runtime.get("document_analysis_status") == "running" or not questions:
        raise build_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            "Clarification is not ready until document analysis finishes.",
            {"document_analysis_status": runtime.get("document_analysis_status")},
        )

    question_map = {item["question_id"]: item for item in task["clarification"]["questions"]}
    for answer_item in payload.answers:
        if answer_item.question_id in question_map:
            question_map[answer_item.question_id]["answer"] = answer_item.answer

    if payload.submitted is not None:
        task["clarification"]["submitted"] = payload.submitted
    submitted = bool(task["clarification"].get("submitted"))
    task["status"] = TaskStatus.pending.value if submitted else TaskStatus.clarifying.value
    if submitted and not task.get("outline_skeleton"):
        update_task_progress(task, "idle", "澄清已提交，可以生成骨架。")
    elif not submitted:
        task["progress"] = None

    task["updated_at"] = now_iso()
    persist_task(task)
    logger.info("Clarification updated task_id=%s submitted=%s", task_id_str, task["clarification"]["submitted"])
    return task_snapshot(task)


def complete_skeleton_generation(task_id: str) -> None:
    try:
        task = fetch_task(task_id)
        if task is None:
            return

        if should_force_fail(task["input"]["topic"]):
            raise RuntimeError("Skeleton generation failed by test marker.")

        skeleton = generate_outline_skeleton(task)
        slides = skeleton["slides"] if isinstance(skeleton, dict) else skeleton
        chapters = skeleton.get("chapters", []) if isinstance(skeleton, dict) else []
        task["outline_skeleton"] = slides
        task["outline_skeleton_chapters"] = chapters
        task["status"] = TaskStatus.pending.value
        update_task_progress(
            task,
            "skeleton_ready",
            "骨架已生成，请确认每页主题。",
            total=len(slides),
            percent=None,
        )
        task["error"] = None
        runtime = task.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
        runtime["last_finished_at"] = now_iso()
        task["runtime"] = runtime
        task["updated_at"] = now_iso()
        persist_task(task)
        logger.info("Skeleton completed task_id=%s slides=%s chapters=%s", task_id, len(slides), len(chapters))
    except Exception as exc:
        logger.exception("Skeleton generation crashed task_id=%s", task_id)
        task = fetch_task(task_id)
        if task is not None:
            task["status"] = TaskStatus.failed.value
            task["error"] = {
                "code": "INTERNAL_ERROR",
                "message": "Skeleton generation failed.",
                "details": {"retryable": True, "reason": str(exc)},
            }
            update_task_progress(task, "failed", "骨架生成失败，请稍后重试。")
            task["updated_at"] = now_iso()
            persist_task(task)


def _align_outline_to_skeleton(outline: dict[str, Any], skeleton: list[dict[str, Any]]) -> dict[str, Any]:
    slides = outline.get("slides", [])
    if not isinstance(slides, list):
        slides = []
    aligned: list[dict[str, Any]] = []
    for idx, skeleton_slide in enumerate(skeleton, start=1):
        existing = slides[idx - 1] if idx - 1 < len(slides) and isinstance(slides[idx - 1], dict) else {}
        aligned.append(
            {
                "slide_id": str(skeleton_slide.get("slide_id") or f"s{idx}"),
                "title": str(skeleton_slide.get("title") or existing.get("title") or f"第{idx}页"),
                "bullets": existing.get("bullets") if isinstance(existing.get("bullets"), list) else [],
                "speaker_notes": str(existing.get("speaker_notes") or ""),
            }
        )
    outline["slides"] = aligned
    meta = outline.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    meta["schema_version"] = settings.outline_schema_version
    meta["outline_skeleton_applied"] = True
    outline["meta"] = meta
    return outline


def complete_slide_generation(task_id: str, concurrency: int = 2) -> None:
    try:
        task = fetch_task(task_id)
        if task is None:
            return
        skeleton = task.get("outline_skeleton")
        if not isinstance(skeleton, list) or not skeleton:
            raise RuntimeError("outline_skeleton is required before slide generation.")

        update_task_progress(task, "llm_page", "正在按骨架生成完整大纲。", current=1, total=len(skeleton), percent=10)
        task["updated_at"] = now_iso()
        persist_task(task)

        if should_force_fail(task["input"]["topic"]):
            raise RuntimeError("Slide generation failed by test marker.")

        def _on_progress(progress_task: dict[str, Any]) -> None:
            progress_task["status"] = TaskStatus.generating.value
            progress_task["updated_at"] = now_iso()
            persist_task(progress_task)

        runtime = task.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
        runtime_concurrency = runtime.get("concurrency") if isinstance(runtime.get("concurrency"), int) else None
        outline = generate_pages_from_skeleton(
            task=task,
            concurrency=runtime_concurrency or concurrency,
            on_progress=_on_progress,
        )
        update_task_progress(task, "assembling", "正在合并每页内容。", current=len(skeleton), total=len(skeleton), percent=90)
        task["outline"] = outline
        task["status"] = TaskStatus.done.value
        update_task_progress(task, "done", "完整大纲已生成。", current=len(skeleton), total=len(skeleton), percent=100)
        task["error"] = None
        runtime["last_finished_at"] = now_iso()
        task["runtime"] = runtime
        task["updated_at"] = now_iso()
        persist_task(task)
        logger.info("Slides completed task_id=%s slides=%s", task_id, len(skeleton))
    except Exception as exc:
        logger.exception("Slide generation crashed task_id=%s", task_id)
        task = fetch_task(task_id)
        if task is not None:
            progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
            phase = progress.get("phase") if isinstance(progress.get("phase"), str) else None
            error_code, error_message, error_details = classify_slide_generation_exception(
                exc,
                phase=phase,
            )
            task["status"] = TaskStatus.failed.value
            task["error"] = {
                "code": error_code,
                "message": error_message,
                "details": error_details,
            }
            update_task_progress(task, "failed", error_message)
            task["updated_at"] = now_iso()
            persist_task(task)


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
            update_task_progress(task, "failed", "生成失败。")
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
        update_task_progress(task, "done", "完整大纲已生成。", percent=100)
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
                update_task_progress(task, "llm_page", "生成失败，已安排自动重试。")
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
                update_task_progress(task, "failed", error_message)
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
        "workflow": "legacy",
        "generation_attempts": int(runtime.get("generation_attempts", 0)) + 1,
        "last_started_at": now_iso(),
        "last_idempotency_key": idempotency_key or None,
        "last_finished_at": runtime.get("last_finished_at"),
    }
    update_task_progress(task, "llm_page", "正在生成完整大纲。")
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

        runtime = task.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
        progress = task.get("progress", {})
        if not isinstance(progress, dict):
            progress = {}
        workflow = str(runtime.get("workflow") or "")
        phase = str(progress.get("phase") or "")
        if not workflow:
            if phase == "skeleton_llm":
                workflow = "skeleton"
            elif phase in ("retrieving_page", "llm_page", "assembling", "saving"):
                workflow = "slides"
            else:
                workflow = "legacy"

        if is_stale:
            task["status"] = TaskStatus.pending.value
            task["updated_at"] = now_iso()
            task["error"] = {
                "code": "INTERNAL_ERROR",
                "message": "Recovered stale generating task, set back to pending.",
                "details": {"recovered": True},
            }
            update_task_progress(task, "idle", "已恢复卡住的后台任务，正在重新排队。")
            persist_task(task)
        if workflow == "skeleton":
            enqueue_skeleton_generation(task_id)
        elif workflow == "slides":
            enqueue_slide_generation(task_id)
        else:
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


@router.delete("/{task_id:uuid}")
def delete_task_endpoint(task_id: UUID) -> dict[str, str]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    get_task_or_404(task_id_str)
    delete_task(task_id_str)
    return {"deleted": task_id_str}


@router.get("/stats/tokens")
def token_usage_stats() -> dict[str, Any]:
    if USE_DB_STORE:
        tasks_list = db_list_tasks(limit=500)
    else:
        tasks_list = list(TASK_STORE.values())

    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    tasks_with_usage = 0
    for task in tasks_list:
        outline = task.get("outline")
        if not isinstance(outline, dict):
            continue
        meta = outline.get("meta")
        if not isinstance(meta, dict):
            continue
        usage = meta.get("token_usage")
        if not isinstance(usage, dict):
            continue
        total_prompt += int(usage.get("prompt_tokens", 0))
        total_completion += int(usage.get("completion_tokens", 0))
        total_tokens += int(usage.get("total_tokens", 0))
        tasks_with_usage += 1

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "tasks_with_usage": tasks_with_usage,
    }


def complete_regenerate_slide(task_id: str, slide_id: str, user_instruction: str | None = None) -> None:
    try:
        task = fetch_task(task_id)
        if task is None:
            return
        outline = task.get("outline")
        if not isinstance(outline, dict):
            return
        slides = outline.get("slides", [])
        if not isinstance(slides, list):
            return

        target_slide = None
        target_idx = -1
        for idx, s in enumerate(slides):
            if isinstance(s, dict) and s.get("slide_id") == slide_id:
                target_slide = dict(s)
                target_idx = idx
                break
        if target_slide is None:
            return

        skeleton_source = task.get("outline_skeleton")
        skeleton_original: dict[str, Any] = {}
        if isinstance(skeleton_source, list):
            for item in skeleton_source:
                if isinstance(item, dict) and item.get("slide_id") == slide_id:
                    skeleton_original = dict(item)
                    break

        skeleton_entry = {
            "slide_id": slide_id,
            "title": target_slide.get("title") or skeleton_original.get("title") or "",
            "intent": skeleton_original.get("intent") or target_slide.get("key_message") or "",
            "user_notes": skeleton_original.get("user_notes") or "",
            "chapter_id": target_slide.get("chapter_id") or skeleton_original.get("chapter_id"),
            "regeneration_instruction": user_instruction or "",
        }

        retrieval_policy = merge_retrieval_policy(task)
        retrieval_depth = retrieval_policy["retrieval_depth"]
        topic = task["input"]["topic"]
        clarification = task.get("clarification")

        from app.services.page_generation import (
            build_evidence_catalog_entry,
            match_bullets_to_evidence,
            retrieve_for_pages,
            _generate_single_page,
        )

        update_task_progress(task, "regenerating_slide", "正在检索该页参考资料。", current=0, total=1, percent=20)
        task["updated_at"] = now_iso()
        persist_task(task)

        retrieval_by_slide, _cache = retrieve_for_pages(
            topic,
            retrieval_depth,
            [skeleton_entry],
            clarification,
            tavily_enabled=bool(retrieval_policy.get("tavily_enabled")),
            force_refresh=bool(retrieval_policy.get("force_refresh")),
            retrieval_policy=retrieval_policy,
            task=task,
        )
        hits = retrieval_by_slide.get(slide_id, [])
        ev_counter = 1
        for hit in hits:
            hit["evidence_id"] = f"ev_re_{ev_counter}"
            ev_counter += 1

        update_task_progress(task, "regenerating_slide", "正在重新生成该页内容。", current=1, total=1, percent=60)
        task["updated_at"] = now_iso()
        persist_task(task)

        new_slide = _generate_single_page(topic, skeleton_entry, hits)
        if skeleton_entry.get("chapter_id"):
            new_slide["chapter_id"] = skeleton_entry["chapter_id"]

        hit_ids = [str(hit.get("evidence_id") or "") for hit in hits if str(hit.get("evidence_id") or "")]
        bullets = new_slide.get("bullets", [])
        if isinstance(bullets, list):
            matched_bullets, _low_confidence = match_bullets_to_evidence(bullets, hits)
            if matched_bullets and hit_ids and not any(isinstance(bullet, dict) and bullet.get("evidence_ids") for bullet in matched_bullets):
                matched_bullets[0]["evidence_ids"] = [hit_ids[0]]
            new_slide["bullets"] = matched_bullets

        # Merge new page into existing outline
        slides[target_idx] = new_slide
        outline["slides"] = slides

        # Rebuild evidence_catalog: remove old evidence for this slide, add new
        new_evidence_ids = set()
        for b in new_slide.get("bullets", []):
            for eid in b.get("evidence_ids", []):
                new_evidence_ids.add(eid)

        old_catalog = outline.get("evidence_catalog", [])
        if not isinstance(old_catalog, list):
            old_catalog = []
        # Remove evidence only referenced by the regenerated slide
        new_catalog = []
        for ev in old_catalog:
            if not isinstance(ev, dict):
                continue
            eid = ev.get("evidence_id", "")
            # Check if any other slide references this evidence
            referenced_elsewhere = False
            for s in slides:
                if s.get("slide_id") == slide_id:
                    continue
                for b in s.get("bullets", []):
                    if eid in b.get("evidence_ids", []):
                        referenced_elsewhere = True
                        break
                if referenced_elsewhere:
                    break
            if referenced_elsewhere and eid not in new_evidence_ids:
                new_catalog.append(ev)
        # Add new evidence
        for hit in hits:
            entry = build_evidence_catalog_entry(hit)
            if entry is not None:
                new_catalog.append(entry)
        outline["evidence_catalog"] = new_catalog
        _rebuild_page_evidence_map(outline)

        task["outline"] = outline
        update_task_progress(task, "done", "单页重生成完成", percent=100)
        task["status"] = TaskStatus.done.value
        task["error"] = None
        task["updated_at"] = now_iso()
        persist_task(task)
        logger.info("Slide regenerated task_id=%s slide_id=%s", task_id, slide_id)
    except Exception as exc:
        logger.exception("Slide regeneration crashed task_id=%s slide_id=%s", task_id, slide_id)
        task = fetch_task(task_id)
        if task is not None:
            task["status"] = TaskStatus.failed.value
            task["error"] = {"code": "INTERNAL_ERROR", "message": str(exc), "details": {}}
            update_task_progress(task, "failed", "单页重生成失败，请稍后重试。")
            task["updated_at"] = now_iso()
            persist_task(task)


def enqueue_regenerate_slide(task_id: str, slide_id: str, user_instruction: str | None = None) -> Future[None]:
    return GENERATION_EXECUTOR.submit(complete_regenerate_slide, task_id, slide_id, user_instruction)


@router.post("/{task_id:uuid}/slides/{slide_id}/regenerate", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
def regenerate_slide(task_id: UUID, slide_id: str, payload: RegenerateSlideRequest | None = None) -> dict[str, Any]:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)

    if task["status"] not in (TaskStatus.done.value, TaskStatus.pending.value):
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "Cannot regenerate in current state.", {"status": task["status"]})

    outline = task.get("outline")
    if not isinstance(outline, dict):
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "No outline to regenerate from.")

    slides = outline.get("slides", [])
    if not isinstance(slides, list):
        slides = []
    found = any(isinstance(s, dict) and s.get("slide_id") == slide_id for s in slides)
    if not found:
        raise build_error(status.HTTP_404_NOT_FOUND, "SLIDE_NOT_FOUND", f"Slide {slide_id} not found in outline.")

    user_instruction = payload.user_instruction if payload else None
    runtime = task.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime["retrieval_policy"] = merge_retrieval_policy(task)
    runtime["workflow"] = "regenerate_slide"
    task["runtime"] = runtime
    task["status"] = TaskStatus.generating.value
    task["progress"] = {"phase": "regenerating_slide", "current": 1, "total": 1, "message": "正在重新生成该页...", "percent": 0}
    task["updated_at"] = now_iso()
    persist_task(task)
    enqueue_regenerate_slide(task_id_str, slide_id, user_instruction)
    return {"task_id": task_id_str, "status": TaskStatus.generating.value, "accepted": True, "slide_id": slide_id}


@router.get("/{task_id:uuid}/export/pptx")
def export_task_pptx(task_id: UUID) -> StreamingResponse:
    task_id_str = str(task_id)
    validate_task_id(task_id_str)
    task = get_task_or_404(task_id_str)
    outline = task.get("outline")
    if not isinstance(outline, dict) or not outline.get("slides"):
        raise build_error(status.HTTP_409_CONFLICT, "INVALID_STATE", "Outline has not been generated yet.")

    pptx_bytes = export_outline_to_pptx(outline)
    safe_title = str(outline.get("title") or task_id_str)[:40]
    filename = f"{safe_title}.pptx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        content=iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
