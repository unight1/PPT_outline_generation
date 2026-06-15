from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from app.database import get_engine

logger = logging.getLogger(__name__)

_TABLE_READY = False


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return

    engine = get_engine()
    if engine is None:
        return

    create_sql = """
    CREATE TABLE IF NOT EXISTS tasks (
      task_id VARCHAR(36) PRIMARY KEY,
      schema_version VARCHAR(32) NULL,
      status VARCHAR(32) NOT NULL,
      created_at VARCHAR(64) NOT NULL,
      updated_at VARCHAR(64) NOT NULL,
      input_json LONGTEXT NOT NULL,
      clarification_json LONGTEXT NOT NULL,
      outline_skeleton_json LONGTEXT NULL,
      outline_skeleton_chapters_json LONGTEXT NULL,
      outline_json LONGTEXT NULL,
      progress_json LONGTEXT NULL,
      error_json LONGTEXT NULL,
      runtime_json LONGTEXT NULL
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))
        for column_name, column_type in (
            ("schema_version", "VARCHAR(32) NULL"),
            ("outline_skeleton_json", "LONGTEXT NULL"),
            ("outline_skeleton_chapters_json", "LONGTEXT NULL"),
            ("progress_json", "LONGTEXT NULL"),
            ("runtime_json", "LONGTEXT NULL"),
        ):
            try:
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}"))
            except Exception as exc:  # pragma: no cover - depends on local MySQL version/message.
                if "Duplicate column" not in str(exc) and "1060" not in str(exc):
                    raise
    _TABLE_READY = True


def _serialize(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _deserialize(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def save_task(task: dict[str, Any]) -> None:
    engine = get_engine()
    if engine is None:
        return
    _ensure_table()
    # Single statement handles both create and update.
    upsert_sql = """
    INSERT INTO tasks (
      task_id, schema_version, status, created_at, updated_at,
      input_json, clarification_json, outline_skeleton_json, outline_skeleton_chapters_json,
      outline_json, progress_json, error_json, runtime_json
    )
    VALUES (
      :task_id, :schema_version, :status, :created_at, :updated_at,
      :input_json, :clarification_json, :outline_skeleton_json, :outline_skeleton_chapters_json,
      :outline_json, :progress_json, :error_json, :runtime_json
    )
    ON DUPLICATE KEY UPDATE
      schema_version = VALUES(schema_version),
      status = VALUES(status),
      updated_at = VALUES(updated_at),
      input_json = VALUES(input_json),
      clarification_json = VALUES(clarification_json),
      outline_skeleton_json = VALUES(outline_skeleton_json),
      outline_skeleton_chapters_json = VALUES(outline_skeleton_chapters_json),
      outline_json = VALUES(outline_json),
      progress_json = VALUES(progress_json),
      error_json = VALUES(error_json),
      runtime_json = VALUES(runtime_json)
    """
    with engine.begin() as conn:
        conn.execute(
            text(upsert_sql),
            {
                "task_id": task["task_id"],
                "schema_version": task.get("schema_version"),
                "status": task["status"],
                "created_at": task["created_at"],
                "updated_at": task["updated_at"],
                "input_json": _serialize(task["input"]),
                "clarification_json": _serialize(task["clarification"]),
                "outline_skeleton_json": _serialize(task.get("outline_skeleton")),
                "outline_skeleton_chapters_json": _serialize(task.get("outline_skeleton_chapters")),
                "outline_json": _serialize(task["outline"]),
                "progress_json": _serialize(task.get("progress")),
                "error_json": _serialize(task["error"]),
                "runtime_json": _serialize(task.get("runtime")),
            },
        )


def get_task(task_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    if engine is None:
        return None
    _ensure_table()
    query_sql = """
    SELECT task_id, schema_version, status, created_at, updated_at, input_json, clarification_json,
           outline_skeleton_json, outline_skeleton_chapters_json, outline_json, progress_json, error_json, runtime_json
    FROM tasks
    WHERE task_id = :task_id
    LIMIT 1
    """
    with engine.begin() as conn:
        row = conn.execute(text(query_sql), {"task_id": task_id}).mappings().first()
    if row is None:
        return None
    return {
        "task_id": row["task_id"],
        "schema_version": row["schema_version"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "input": _deserialize(row["input_json"]),
        "clarification": _deserialize(row["clarification_json"]),
        "outline_skeleton": _deserialize(row["outline_skeleton_json"]),
        "outline_skeleton_chapters": _deserialize(row["outline_skeleton_chapters_json"]),
        "outline": _deserialize(row["outline_json"]),
        "progress": _deserialize(row["progress_json"]),
        "error": _deserialize(row["error_json"]),
        "runtime": _deserialize(row["runtime_json"]),
    }


def list_tasks_by_status(status: str, limit: int = 100) -> list[dict[str, Any]]:
    engine = get_engine()
    if engine is None:
        return []
    _ensure_table()
    query_sql = """
    SELECT task_id, schema_version, status, created_at, updated_at, input_json, clarification_json,
           outline_skeleton_json, outline_skeleton_chapters_json, outline_json, progress_json, error_json, runtime_json
    FROM tasks
    WHERE status = :status
    ORDER BY updated_at DESC
    LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query_sql), {"status": status, "limit": limit}).mappings().all()

    tasks: list[dict[str, Any]] = []
    for row in rows:
        tasks.append(
            {
                "task_id": row["task_id"],
                "schema_version": row["schema_version"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "input": _deserialize(row["input_json"]),
                "clarification": _deserialize(row["clarification_json"]),
                "outline_skeleton": _deserialize(row["outline_skeleton_json"]),
                "outline_skeleton_chapters": _deserialize(row["outline_skeleton_chapters_json"]),
                "outline": _deserialize(row["outline_json"]),
                "progress": _deserialize(row["progress_json"]),
                "error": _deserialize(row["error_json"]),
                "runtime": _deserialize(row["runtime_json"]),
            }
        )
    return tasks


def list_tasks(limit: int = 200) -> list[dict[str, Any]]:
    engine = get_engine()
    if engine is None:
        return []
    _ensure_table()
    query_sql = """
    SELECT task_id, schema_version, status, created_at, updated_at, input_json, clarification_json,
           outline_skeleton_json, outline_skeleton_chapters_json, outline_json, progress_json, error_json, runtime_json
    FROM tasks
    ORDER BY updated_at DESC
    LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query_sql), {"limit": limit}).mappings().all()

    tasks: list[dict[str, Any]] = []
    for row in rows:
        tasks.append(
            {
                "task_id": row["task_id"],
                "schema_version": row["schema_version"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "input": _deserialize(row["input_json"]),
                "clarification": _deserialize(row["clarification_json"]),
                "outline_skeleton": _deserialize(row["outline_skeleton_json"]),
                "outline_skeleton_chapters": _deserialize(row["outline_skeleton_chapters_json"]),
                "outline": _deserialize(row["outline_json"]),
                "progress": _deserialize(row["progress_json"]),
                "error": _deserialize(row["error_json"]),
                "runtime": _deserialize(row["runtime_json"]),
            }
        )
    return tasks


def delete_task(task_id: str) -> bool:
    engine = get_engine()
    if engine is None:
        return False
    _ensure_table()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM tasks WHERE task_id = :task_id"),
            {"task_id": task_id},
        )
    return bool(result.rowcount)


def store_available() -> bool:
    # Route layer decides fallback behavior based on this check.
    available = get_engine() is not None
    if not available:
        logger.warning("DATABASE_URL is not configured. Falling back to in-memory task store.")
    return available
