from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

_engine: Engine | None = None


def get_engine() -> Engine | None:
    global _engine
    if not settings.database_url:
        return None
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine


def check_mysql() -> bool:
    engine = get_engine()
    if engine is None:
        return False
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
