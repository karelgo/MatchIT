"""Application factory. Services are built once and hung off `app.state` so tests
can construct the app with fakes."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.embeddings import EmbeddingModel, build_embedding_model
from app.ai.llm import ChatModel, build_chat_model
from app.api.v1 import assignments, auth, profiles
from app.core.config import Settings, get_settings
from app.services.apple import AppleIdentityVerifier, JWKSAppleVerifier
from app.services.auth import AuthService
from app.services.intake import IntakeService
from app.services.matching import MatchingEngine
from app.services.trust import TrustScoreService
from app.services.vector import VectorIndex, build_vector_index

structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()]
)


def create_app(
    settings: Settings | None = None,
    *,
    chat_model: ChatModel | None = None,
    embedding_model: EmbeddingModel | None = None,
    vector_index: VectorIndex | None = None,
    apple_verifier: AppleIdentityVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    chat = chat_model or build_chat_model(settings)
    embeddings = embedding_model or build_embedding_model(settings)
    index = vector_index or build_vector_index(settings)

    app.state.settings = settings
    app.state.auth_service = AuthService(settings, apple_verifier or JWKSAppleVerifier(settings))
    app.state.intake_service = IntakeService(chat)
    app.state.matching_engine = MatchingEngine(embeddings, index)
    app.state.trust_service = TrustScoreService()

    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(profiles.router, prefix=api_prefix)
    app.include_router(assignments.router, prefix=api_prefix)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app
