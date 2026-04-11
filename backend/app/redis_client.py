import redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _client
    if not settings.redis_url:
        return None
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def check_redis() -> bool:
    client = get_redis()
    if client is None:
        return False
    return client.ping()
