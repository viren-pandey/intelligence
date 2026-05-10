import json
from typing import Any
import redis.asyncio as aioredis
from core.config import settings

_redis = None


async def init_redis():
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )


async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None


def get_client() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


async def get(key: str) -> Any:
    val = await get_client().get(key)
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


async def set(key: str, value: Any, ex: int | None = None):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await get_client().set(key, value, ex=ex)


async def delete(key: str):
    await get_client().delete(key)


async def publish(channel: str, message: Any):
    if isinstance(message, (dict, list)):
        message = json.dumps(message)
    await get_client().publish(channel, message)


async def subscribe(channel: str):
    pubsub = get_client().pubsub()
    await pubsub.subscribe(channel)
    return pubsub
