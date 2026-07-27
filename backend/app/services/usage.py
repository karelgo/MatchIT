"""Per-feature AI usage metering.

Counters, not database rows: this sits on the hot path of every AI call, and the
question it answers ("which feature is burning the budget") is aggregate. Redis
so the count is shared across replicas.
"""

from collections import Counter
from typing import Protocol

from app.ai.llm import ChatModel, T
from app.core.config import Settings


class UsageCounter(Protocol):
    async def increment(self, feature: str) -> None: ...

    async def totals(self) -> dict[str, int]: ...


class RedisUsageCounter:
    KEY = "ai_usage"

    def __init__(self, url: str):
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def increment(self, feature: str) -> None:
        await self._redis.hincrby(self.KEY, feature, 1)

    async def totals(self) -> dict[str, int]:
        raw = await self._redis.hgetall(self.KEY)
        return {feature: int(count) for feature, count in raw.items()}


class InMemoryUsageCounter:
    def __init__(self):
        self._counts: Counter[str] = Counter()

    async def increment(self, feature: str) -> None:
        self._counts[feature] += 1

    async def totals(self) -> dict[str, int]:
        return dict(self._counts)


class MeteredChatModel:
    """Wraps a ChatModel, attributing every call to one feature.

    Labelling happens at construction — each service is handed its own labelled
    model — so no call site has to remember to pass a feature name.
    """

    def __init__(self, inner: ChatModel, *, feature: str, counter: UsageCounter):
        self._inner = inner
        self._feature = feature
        self._counter = counter

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        await self._counter.increment(self._feature)
        return await self._inner.complete_structured(
            system=system, user=user, schema=schema, max_tokens=max_tokens
        )


def build_usage_counter(settings: Settings) -> UsageCounter:
    if settings.usage_counter_backend == "redis":
        return RedisUsageCounter(settings.redis_url)
    if settings.usage_counter_backend == "memory":
        return InMemoryUsageCounter()
    raise ValueError(f"unknown usage_counter_backend: {settings.usage_counter_backend}")
