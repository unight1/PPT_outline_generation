from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/eval", tags=["evaluation"])
logger = logging.getLogger(__name__)

_EVAL_DATA_DIR = Path(__file__).resolve().parents[4] / "docs" / "evaluation"


class EvalCase(BaseModel):
    eval_id: str = Field(default_factory=lambda: f"eval_{uuid4().hex[:6]}")
    topic: str = Field(min_length=1)
    source_type: Literal["short_topic", "long_document"] = "short_topic"
    document_text: str | None = None
    expected_depth: Literal["L0", "L1", "L2"] = "L1"
    constraints: list[str] = Field(default_factory=list)
    priority: Literal["low", "medium", "high"] = "medium"
    status: Literal["pending", "generating", "done", "failed"] = "pending"
    task_id: str | None = None
    score: int | None = Field(default=None, ge=1, le=5)
    evaluator: str | None = None
    evidence_coverage: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class EvalCaseList(BaseModel):
    items: list[EvalCase]
    total: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_dataset() -> list[dict[str, Any]]:
    path = _EVAL_DATA_DIR / "dataset_v0.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_dataset(items: list[dict[str, Any]]) -> None:
    _EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVAL_DATA_DIR / "dataset_v0.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_index(eval_id: str) -> int | None:
    items = _load_dataset()
    for idx, item in enumerate(items):
        if item.get("eval_id") == eval_id:
            return idx
    return None


@router.get("", response_model=EvalCaseList)
def list_eval_cases() -> EvalCaseList:
    items = _load_dataset()
    return EvalCaseList(items=items, total=len(items))


@router.post("", response_model=EvalCase, status_code=status.HTTP_201_CREATED)
def create_eval_case(payload: EvalCase) -> EvalCase:
    items = _load_dataset()
    item = payload.model_dump()
    item["created_at"] = item.get("created_at") or _now_iso()
    item["updated_at"] = _now_iso()
    items.append(item)
    _save_dataset(items)
    logger.info("Eval case created eval_id=%s topic=%s", item["eval_id"], item["topic"])
    return EvalCase(**item)


@router.get("/{eval_id}", response_model=EvalCase)
def get_eval_case(eval_id: str) -> EvalCase:
    idx = _find_index(eval_id)
    if idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "EVAL_NOT_FOUND", "message": f"Eval case {eval_id} not found.", "details": {}}},
        )
    return EvalCase(**_load_dataset()[idx])


@router.patch("/{eval_id}", response_model=EvalCase)
def update_eval_case(eval_id: str, payload: EvalCase) -> EvalCase:
    idx = _find_index(eval_id)
    if idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "EVAL_NOT_FOUND", "message": f"Eval case {eval_id} not found.", "details": {}}},
        )
    items = _load_dataset()
    existing = items[idx]
    updated = payload.model_dump()
    updated["eval_id"] = eval_id
    updated["created_at"] = existing.get("created_at") or updated.get("created_at") or _now_iso()
    updated["updated_at"] = _now_iso()
    items[idx] = updated
    _save_dataset(items)
    return EvalCase(**updated)


@router.delete("/{eval_id}")
def delete_eval_case(eval_id: str) -> dict[str, str]:
    idx = _find_index(eval_id)
    if idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "EVAL_NOT_FOUND", "message": f"Eval case {eval_id} not found.", "details": {}}},
        )
    items = _load_dataset()
    items.pop(idx)
    _save_dataset(items)
    return {"deleted": eval_id}


@router.post("/{eval_id}/score", response_model=EvalCase)
def score_eval_case(eval_id: str, payload: dict[str, Any]) -> EvalCase:
    idx = _find_index(eval_id)
    if idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "EVAL_NOT_FOUND", "message": f"Eval case {eval_id} not found.", "details": {}}},
        )
    items = _load_dataset()
    item = items[idx]

    if "score" in payload:
        item["score"] = int(payload["score"])
    if "evaluator" in payload:
        item["evaluator"] = str(payload["evaluator"])
    if "evidence_coverage" in payload:
        item["evidence_coverage"] = float(payload["evidence_coverage"])
    if "notes" in payload:
        item["notes"] = str(payload["notes"])
    if "status" in payload:
        item["status"] = str(payload["status"])
    if "task_id" in payload:
        item["task_id"] = str(payload["task_id"])

    item["updated_at"] = _now_iso()
    items[idx] = item
    _save_dataset(items)
    return EvalCase(**item)


@router.get("/stats/summary")
def eval_stats_summary() -> dict[str, Any]:
    items = _load_dataset()
    total = len(items)
    scored = [i for i in items if i.get("score") is not None]
    avg_score = (
        sum(i["score"] for i in scored) / len(scored) if scored else None
    )
    by_priority = {"high": 0, "medium": 0, "low": 0}
    by_status = {"pending": 0, "generating": 0, "done": 0, "failed": 0}
    for i in items:
        p = str(i.get("priority", "medium"))
        s = str(i.get("status", "pending"))
        if p in by_priority:
            by_priority[p] += 1
        if s in by_status:
            by_status[s] += 1

    return {
        "total": total,
        "scored": len(scored),
        "average_score": round(avg_score, 2) if avg_score is not None else None,
        "by_priority": by_priority,
        "by_status": by_status,
    }
