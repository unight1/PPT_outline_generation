from fastapi import APIRouter

from app.config import settings
from app.database import check_mysql
from app.redis_client import check_redis

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ppt-outline-api"}


@router.get("/health/ready")
def ready() -> dict:
    """Reports dependency status. Useful after `docker compose up`."""
    mysql_ok: bool | None = None
    if settings.database_url:
        try:
            mysql_ok = check_mysql()
        except Exception:
            mysql_ok = False

    redis_ok: bool | None = None
    if settings.redis_url:
        try:
            redis_ok = check_redis()
        except Exception:
            redis_ok = False

    return {
        "mysql": mysql_ok,
        "redis": redis_ok,
    }
