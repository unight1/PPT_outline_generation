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
      status VARCHAR(32) NOT NULL,
      created_at VARCHAR(64) NOT NULL,
      updated_at VARCHAR(64) NOT NULL,
      input_json LONGTEXT NOT NULL,
      clarification_json LONGTEXT NOT NULL,
      outline_json LONGTEXT NULL,
      error_json LONGTEXT NULL
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))
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
      task_id, status, created_at, updated_at,
      input_json, clarification_json, outline_json, error_json
    )
    VALUES (
      :task_id, :status, :created_at, :updated_at,
      :input_json, :clarification_json, :outline_json, :error_json
    )
    ON DUPLICATE KEY UPDATE
      status = VALUES(status),
      updated_at = VALUES(updated_at),
      input_json = VALUES(input_json),
      clarification_json = VALUES(clarification_json),
      outline_json = VALUES(outline_json),
      error_json = VALUES(error_json)
    """
    with engine.begin() as conn:
        conn.execute(
            text(upsert_sql),
            {
                "task_id": task["task_id"],
                "status": task["status"],
                "created_at": task["created_at"],
                "updated_at": task["updated_at"],
                "input_json": _serialize(task["input"]),
                "clarification_json": _serialize(task["clarification"]),
                "outline_json": _serialize(task["outline"]),
                "error_json": _serialize(task["error"]),
            },
        )


def get_task(task_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    if engine is None:
        return None
    _ensure_table()
    query_sql = """
    SELECT task_id, status, created_at, updated_at, input_json, clarification_json, outline_json, error_json
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
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "input": _deserialize(row["input_json"]),
        "clarification": _deserialize(row["clarification_json"]),
        "outline": _deserialize(row["outline_json"]),
        "error": _deserialize(row["error_json"]),
    }


def store_available() -> bool:
    # Route layer decides fallback behavior based on this check.
    available = get_engine() is not None
    if not available:
        logger.warning("DATABASE_URL is not configured. Falling back to in-memory task store.")
    return available
