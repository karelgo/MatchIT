"""Fixed-window rate limiting behind a protocol.

Redis in production so the limit is shared across API replicas; in-memory for
tests and single-node development. A per-replica limiter would let an attacker
multiply their budget by the replica count, so the backend choice is a real
security property, not a detail.
"""

import time
from collections import defaultdict
from typing import Protocol

from app.core.config import Settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded, retry in {retry_after}s")


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Record one request; raise RateLimitExceeded when over budget."""
        ...


class RedisRateLimiter:
    def __init__(self, url: str):
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        # Bucket by window so the key expires on its own; INCR+EXPIRE in one
        # round trip keeps this cheap enough to sit in front of every request.
        window = int(time.time()) // window_seconds
        redis_key = f"ratelimit:{key}:{window}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds)
            count, _ = await pipe.execute()
        if int(count) > limit:
            raise RateLimitExceeded(window_seconds - int(time.time()) % window_seconds)


class InMemoryRateLimiter:
    """Single-process limiter for tests and local development."""

    def __init__(self):
        self._counts: dict[tuple[str, int], int] = defaultdict(int)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        window = int(time.time()) // window_seconds
        self._counts[(key, window)] += 1
        if self._counts[(key, window)] > limit:
            raise RateLimitExceeded(window_seconds - int(time.time()) % window_seconds)

    def reset(self) -> None:
        self._counts.clear()


class NullRateLimiter:
    """Disables limiting; used by tests that are not exercising it."""

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        return None


def build_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter(settings.redis_url)
    if settings.rate_limit_backend == "memory":
        return InMemoryRateLimiter()
    if settings.rate_limit_backend == "off":
        return NullRateLimiter()
    raise ValueError(f"unknown rate_limit_backend: {settings.rate_limit_backend}")
