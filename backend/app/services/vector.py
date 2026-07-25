"""Vector search behind a protocol: Qdrant in production, in-memory in tests."""

import math
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings

SPECIALISTS_COLLECTION = "specialists"


@dataclass
class VectorHit:
    id: uuid.UUID
    score: float
    payload: dict


class VectorIndex(Protocol):
    async def upsert(self, collection: str, id: uuid.UUID, vector: list[float], payload: dict): ...

    async def search(self, collection: str, vector: list[float], limit: int) -> list[VectorHit]: ...

    async def delete(self, collection: str, id: uuid.UUID) -> None: ...


class QdrantIndex:
    def __init__(self, url: str, api_key: str, dimensions: int):
        from qdrant_client import AsyncQdrantClient

        self._client = AsyncQdrantClient(url=url, api_key=api_key or None)
        self._dimensions = dimensions

    async def ensure_collections(self) -> None:
        from qdrant_client import models

        if not await self._client.collection_exists(SPECIALISTS_COLLECTION):
            await self._client.create_collection(
                collection_name=SPECIALISTS_COLLECTION,
                vectors_config=models.VectorParams(
                    size=self._dimensions, distance=models.Distance.COSINE
                ),
            )

    async def upsert(self, collection: str, id: uuid.UUID, vector: list[float], payload: dict):
        from qdrant_client import models

        await self._client.upsert(
            collection_name=collection,
            points=[models.PointStruct(id=str(id), vector=vector, payload=payload)],
        )

    async def search(self, collection: str, vector: list[float], limit: int) -> list[VectorHit]:
        response = await self._client.query_points(
            collection_name=collection, query=vector, limit=limit, with_payload=True
        )
        return [
            VectorHit(id=uuid.UUID(str(p.id)), score=p.score, payload=p.payload or {})
            for p in response.points
        ]

    async def delete(self, collection: str, id: uuid.UUID) -> None:
        from qdrant_client import models

        await self._client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=[str(id)]),
        )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class InMemoryVectorIndex:
    """Reference implementation for tests and local development without Qdrant."""

    store: dict[str, dict[uuid.UUID, tuple[list[float], dict]]] = field(default_factory=dict)

    async def upsert(self, collection: str, id: uuid.UUID, vector: list[float], payload: dict):
        self.store.setdefault(collection, {})[id] = (vector, payload)

    async def search(self, collection: str, vector: list[float], limit: int) -> list[VectorHit]:
        hits = [
            VectorHit(id=id, score=cosine_similarity(vector, stored), payload=payload)
            for id, (stored, payload) in self.store.get(collection, {}).items()
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    async def delete(self, collection: str, id: uuid.UUID) -> None:
        self.store.get(collection, {}).pop(id, None)


def build_vector_index(settings: Settings) -> VectorIndex:
    if settings.vector_backend == "qdrant":
        return QdrantIndex(
            settings.qdrant_url, settings.qdrant_api_key, settings.embedding_dimensions
        )
    if settings.vector_backend == "memory":
        return InMemoryVectorIndex()
    raise ValueError(f"unknown vector_backend: {settings.vector_backend}")
