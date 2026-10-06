"""Redis connection helpers and queue utilities."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

INGESTION_QUEUE_KEY = "docmind:ingestion:queue"

_redis_client: aioredis.Redis | None = None
_in_memory_queue: list[dict[str, Any]] = []


async def get_redis() -> aioredis.Redis | None:
    """Get or create singleton async Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        try:
            _redis_client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.health_timeout_seconds,
            )
            await _redis_client.ping()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis not reachable (%s); queue operating in fallback mode", exc)
            _redis_client = None
    return _redis_client


async def enqueue_ingestion_job(
    document_id: str,
    version_id: str,
    extra_meta: dict[str, Any] | None = None,
) -> bool:
    """Push an ingestion task to the Redis ingestion queue."""
    payload: dict[str, Any] = {
        "document_id": document_id,
        "version_id": version_id,
        "metadata": extra_meta or {},
    }
    client = await get_redis()
    if client is not None:
        try:
            await client.lpush(INGESTION_QUEUE_KEY, json.dumps(payload))
            logger.info("Enqueued ingestion job for document %s to Redis", document_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis lpush failed (%s); storing in memory fallback", exc)

    _in_memory_queue.append(payload)
    logger.info("Enqueued ingestion job for document %s to memory fallback queue", document_id)
    return True


async def pop_ingestion_job() -> dict[str, Any] | None:
    """Pop next ingestion job from Redis or memory fallback."""
    client = await get_redis()
    if client is not None:
        try:
            raw = await client.rpop(INGESTION_QUEUE_KEY)
            if raw and isinstance(raw, str):
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception:  # noqa: BLE001
            pass

    if _in_memory_queue:
        return _in_memory_queue.pop(0)
    return None
