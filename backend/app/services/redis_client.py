"""Redis connection helpers and queue utilities."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import RedisBackend, get_settings

logger = logging.getLogger(__name__)

INGESTION_QUEUE_KEY = "docmind:ingestion:queue"

_redis_client: aioredis.Redis | None = None
_in_memory_queue: list[dict[str, Any]] = []


async def get_redis() -> aioredis.Redis | None:
    """Get or create singleton async Redis client.

    If REDIS_BACKEND=redis and Redis is unreachable, fails loudly by raising RuntimeError.
    If REDIS_BACKEND=memory, returns None.
    """
    global _redis_client
    settings = get_settings()
    if settings.redis_backend == RedisBackend.MEMORY:
        return None

    if _redis_client is None:
        try:
            client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.health_timeout_seconds,
            )
            await client.ping()
            _redis_client = client
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Redis configured (REDIS_BACKEND=redis) but unreachable at %s: %s",
                settings.redis_url,
                exc,
            )
            raise RuntimeError(
                f"Redis is configured (REDIS_BACKEND=redis) but unreachable at {settings.redis_url}: {exc}"
            ) from exc
    return _redis_client


async def close_redis() -> None:
    """Close active Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def enqueue_ingestion_job(
    document_id: str,
    version_id: str,
    extra_meta: dict[str, Any] | None = None,
) -> bool:
    """Push an ingestion task to the queue (Redis or memory)."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "document_id": document_id,
        "version_id": version_id,
        "metadata": extra_meta or {},
    }
    if settings.redis_backend == RedisBackend.REDIS:
        client = await get_redis()
        if client is None:
            raise RuntimeError("Redis client returned None while REDIS_BACKEND=redis")
        try:
            await client.lpush(INGESTION_QUEUE_KEY, json.dumps(payload))
            logger.info("Enqueued ingestion job for document %s to Redis", document_id)
            return True
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to enqueue ingestion job to Redis: {exc}") from exc
    else:
        _in_memory_queue.append(payload)
        logger.info("Enqueued ingestion job for document %s to memory queue", document_id)
        return True


async def pop_ingestion_job(timeout: int = 1) -> dict[str, Any] | None:
    """Pop next ingestion job from Redis or memory queue."""
    settings = get_settings()
    if settings.redis_backend == RedisBackend.REDIS:
        client = await get_redis()
        if client is None:
            raise RuntimeError("Redis client returned None while REDIS_BACKEND=redis")
        try:
            res = await client.brpop(INGESTION_QUEUE_KEY, timeout=timeout)
            if res:
                _, raw = res
                if raw and isinstance(raw, str):
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            return None
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to pop ingestion job from Redis: {exc}") from exc
    else:
        if _in_memory_queue:
            return _in_memory_queue.pop(0)
        return None
