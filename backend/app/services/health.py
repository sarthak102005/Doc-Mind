"""Dependency health checks for /health.

Each check is small, has its own timeout, and never raises: a failing
dependency is reported as ``down`` with a short error string so the endpoint
itself stays up. Secrets are never included in the error text.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

import httpx
import psycopg
import redis.asyncio as aioredis
from pydantic import BaseModel

from app.core.config import Settings

Status = Literal["up", "down"]


class ComponentHealth(BaseModel):
    status: Status
    latency_ms: float
    detail: str | None = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, ComponentHealth]


Check = Callable[[Settings], Awaitable[str | None]]


def _sync_check_postgres(settings: Settings) -> str | None:
    with (
        psycopg.connect(
            settings.database_url, connect_timeout=max(1, int(settings.health_timeout_seconds))
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT version()")
        row = cur.fetchone()
        return str(row[0]).split(" on ")[0] if row else None


async def check_postgres(settings: Settings) -> str | None:
    return await asyncio.to_thread(_sync_check_postgres, settings)


async def check_qdrant(settings: Settings) -> str | None:
    headers = {}
    if settings.qdrant_api_key is not None and settings.qdrant_api_key.get_secret_value():
        headers["api-key"] = settings.qdrant_api_key.get_secret_value()
    async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
        ready = await client.get(f"{settings.qdrant_url.rstrip('/')}/readyz", headers=headers)
        ready.raise_for_status()
        info = await client.get(settings.qdrant_url.rstrip("/") + "/", headers=headers)
        info.raise_for_status()
        return f"qdrant {info.json().get('version', '?')}"


async def check_redis(settings: Settings) -> str | None:
    client = aioredis.from_url(
        settings.redis_url, socket_connect_timeout=settings.health_timeout_seconds
    )
    try:
        pong = await client.ping()
        if not pong:
            raise RuntimeError("PING returned false")
        info = await client.info("server")
        return f"redis {info.get('redis_version', '?')}"
    finally:
        await client.aclose()


async def check_minio(settings: Settings) -> str | None:
    async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
        resp = await client.get(f"{settings.minio_url}/minio/health/ready")
        resp.raise_for_status()
        return "ready"


DEFAULT_CHECKS: dict[str, Check] = {
    "postgres": check_postgres,
    "qdrant": check_qdrant,
    "redis": check_redis,
    "minio": check_minio,
}


async def _run_one(name: str, check: Check, settings: Settings) -> tuple[str, ComponentHealth]:
    start = time.perf_counter()
    try:
        detail = await asyncio.wait_for(check(settings), timeout=settings.health_timeout_seconds + 1)
        status: Status = "up"
    except Exception as exc:  # noqa: BLE001 - health must never raise
        detail = f"{type(exc).__name__}: {str(exc)[:200]}"
        status = "down"
    latency = round((time.perf_counter() - start) * 1000, 1)
    return name, ComponentHealth(status=status, latency_ms=latency, detail=detail)


async def collect_health(settings: Settings, checks: dict[str, Check] | None = None) -> HealthReport:
    checks = checks if checks is not None else DEFAULT_CHECKS
    results = await asyncio.gather(*(_run_one(n, c, settings) for n, c in checks.items()))
    components = dict(results)
    overall: Literal["ok", "degraded"] = (
        "ok" if all(c.status == "up" for c in components.values()) else "degraded"
    )
    return HealthReport(status=overall, components=components)
