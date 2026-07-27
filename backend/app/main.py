"""Application factory. Services are built once and hung off `app.state` so tests
can construct the app with fakes."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embeddings import EmbeddingModel, build_embedding_model
from app.ai.llm import ChatModel, build_chat_model
from app.api.v1 import (
    admin,
    assignments,
    auth,
    chat,
    contracts,
    devices,
    interviews,
    invoices,
    privacy,
    profiles,
)
from app.core.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.services.analytics import AnalyticsService
from app.services.apple import AppleIdentityVerifier, JWKSAppleVerifier
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.contract import ContractService
from app.services.enrichment import EnrichmentService
from app.services.github import GitHubClient, build_github_client
from app.services.intake import IntakeService
from app.services.interview import InterviewService
from app.services.matching import MatchingEngine
from app.services.notifications import PushSender, build_push_sender
from app.services.notifier import Notifier
from app.services.payments import PaymentProvider, build_payment_provider
from app.services.privacy import PrivacyService
from app.services.pubsub import PubSub, build_pubsub
from app.services.ratelimit import RateLimiter, build_rate_limiter
from app.services.team import TeamBuilderService
from app.services.trust import TrustScoreService
from app.services.usage import MeteredChatModel, UsageCounter, build_usage_counter
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
    pubsub: PubSub | None = None,
    rate_limiter: RateLimiter | None = None,
    github_client: GitHubClient | None = None,
    usage_counter: UsageCounter | None = None,
    payment_provider: PaymentProvider | None = None,
    push_sender: PushSender | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
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

    llm = chat_model or build_chat_model(settings)
    embeddings = embedding_model or build_embedding_model(settings)
    index = vector_index or build_vector_index(settings)

    app.state.settings = settings
    app.state.auth_service = AuthService(settings, apple_verifier or JWKSAppleVerifier(settings))
    counter = usage_counter or build_usage_counter(settings)
    app.state.usage_counter = counter

    def metered(feature: str) -> ChatModel:
        """Label AI usage at construction, so no call site has to remember to."""
        return MeteredChatModel(llm, feature=feature, counter=counter)

    app.state.intake_service = IntakeService(metered("intake"))
    app.state.interview_service = InterviewService(metered("interview"))
    app.state.contract_service = ContractService(metered("contract"))
    app.state.enrichment_service = EnrichmentService(
        metered("enrichment"), github_client or build_github_client()
    )
    app.state.analytics_service = AnalyticsService()
    app.state.payment_provider = payment_provider or build_payment_provider(settings)
    matching_engine = MatchingEngine(embeddings, index)
    app.state.matching_engine = matching_engine
    app.state.team_builder = TeamBuilderService(metered("team_builder"), matching_engine)
    app.state.trust_service = TrustScoreService()
    app.state.audit_service = AuditService()
    app.state.privacy_service = PrivacyService()
    app.state.rate_limiter = rate_limiter or build_rate_limiter(settings)
    app.state.notifier = Notifier(push_sender or build_push_sender(settings))
    app.state.chat_service = ChatService(pubsub or build_pubsub(settings), app.state.notifier)
    # WebSockets open their own short-lived sessions rather than holding a
    # request-scoped one for the socket's lifetime (see api/v1/chat.py).
    app.state.sessionmaker = sessionmaker or get_sessionmaker()

    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(profiles.router, prefix=api_prefix)
    app.include_router(assignments.router, prefix=api_prefix)
    app.include_router(chat.router, prefix=api_prefix)
    app.include_router(interviews.router, prefix=api_prefix)
    app.include_router(contracts.router, prefix=api_prefix)
    app.include_router(privacy.router, prefix=api_prefix)
    app.include_router(invoices.router, prefix=api_prefix)
    app.include_router(devices.router, prefix=api_prefix)
    app.include_router(admin.router, prefix=api_prefix)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app
