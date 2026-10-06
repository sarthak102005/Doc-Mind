"""Rate limiter for FastAPI using Redis with in-memory fallback."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.services.redis_client import get_redis

# In-memory fallback: key -> list of timestamp floats
_memory_rate_buckets: dict[str, list[float]] = defaultdict(list)


class RateLimiter:
    """Rate limiter dependency.

    Example:
        @router.post("/upload", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
    """

    def __init__(self, times: int = 60, seconds: int = 60) -> None:
        self.times = times
        self.seconds = seconds

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        key = f"rate_limit:{client_ip}:{path}"

        redis = await get_redis()
        if redis is not None:
            try:
                current = await redis.incr(key)
                if current == 1:
                    await redis.expire(key, self.seconds)
                if current > self.times:
                    ttl = await redis.ttl(key)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded. Please try again later.",
                        headers={"Retry-After": str(max(1, ttl))},
                    )
                return
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001
                # If Redis fails mid-operation, fall through to in-memory check
                pass

        # In-memory sliding window check
        now = time.time()
        cutoff = now - self.seconds
        timestamps = _memory_rate_buckets[key]
        _memory_rate_buckets[key] = [t for t in timestamps if t > cutoff]
        if len(_memory_rate_buckets[key]) >= self.times:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(self.seconds)},
            )
        _memory_rate_buckets[key].append(now)


def rate_limit(times: int = 60, seconds: int = 60) -> RateLimiter:
    return RateLimiter(times=times, seconds=seconds)
