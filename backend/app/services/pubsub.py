"""Broadcast fan-out behind a protocol: Redis in production, in-memory otherwise.

Chat (and later notifications) publish JSON payloads to a channel; every
subscriber on any API replica receives them. The in-memory implementation covers
tests and single-node development.
"""

import asyncio
import contextlib
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Protocol

from app.core.config import Settings


class PubSub(Protocol):
    async def publish(self, channel: str, payload: str) -> None: ...

    def subscribe(
        self, channel: str
    ) -> contextlib.AbstractAsyncContextManager[AsyncIterator[str]]: ...


class RedisPubSub:
    def __init__(self, url: str):
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def publish(self, channel: str, payload: str) -> None:
        await self._redis.publish(channel, payload)

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[str]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)

        async def stream() -> AsyncIterator[str]:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield message["data"]

        try:
            yield stream()
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


class _Subscriber:
    """Identity-hashed inbox. A bare deque cannot live in a set (unhashable)."""

    __slots__ = ("queue",)

    def __init__(self):
        self.queue: deque[str] = deque()


class InMemoryPubSub:
    """Thread- and event-loop-agnostic broadcast for tests and local development.

    Subscribers poll a plain deque, so publisher and subscriber may live on
    different event loops (as happens under Starlette's TestClient portals).
    """

    POLL_INTERVAL = 0.01

    def __init__(self):
        self._subscribers: dict[str, set[_Subscriber]] = defaultdict(set)

    async def publish(self, channel: str, payload: str) -> None:
        for subscriber in list(self._subscribers.get(channel, ())):
            subscriber.queue.append(payload)

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[str]]:
        subscriber = _Subscriber()
        self._subscribers[channel].add(subscriber)

        async def stream() -> AsyncIterator[str]:
            while True:
                try:
                    yield subscriber.queue.popleft()
                except IndexError:
                    await asyncio.sleep(InMemoryPubSub.POLL_INTERVAL)

        try:
            yield stream()
        finally:
            self._subscribers[channel].discard(subscriber)


def build_pubsub(settings: Settings) -> PubSub:
    if settings.pubsub_backend == "redis":
        return RedisPubSub(settings.redis_url)
    if settings.pubsub_backend == "memory":
        return InMemoryPubSub()
    raise ValueError(f"unknown pubsub_backend: {settings.pubsub_backend}")
