"""Provider-agnostic text embeddings with a deterministic offline fake."""

import hashlib
import math
from typing import Protocol

from app.core.config import Settings


class EmbeddingModel(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingModel:
    def __init__(self, api_key: str, model: str, dimensions: int):
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model, input=texts, dimensions=self.dimensions
        )
        return [item.embedding for item in response.data]


class FakeEmbeddingModel:
    """Hash-bucketed bag-of-words embedding.

    Deterministic and cheap, yet preserves the property tests rely on: texts
    sharing more tokens have higher cosine similarity.
    """

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode()).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                vector[index] += 1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        return vectors


def build_embedding_model(settings: Settings) -> EmbeddingModel:
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingModel(
            settings.openai_api_key, settings.embedding_model, settings.embedding_dimensions
        )
    if settings.embedding_provider == "fake":
        return FakeEmbeddingModel()
    raise ValueError(f"unknown embedding_provider: {settings.embedding_provider}")
