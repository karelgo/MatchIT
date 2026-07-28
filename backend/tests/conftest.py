import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.embeddings import FakeEmbeddingModel
from app.ai.llm import FakeChatModel
from app.ai.schemas import AssignmentRequirements, BudgetRange, RoleRequirement
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.apple import AppleIdentity
from app.services.github import FakeGitHubClient, Repository
from app.services.notifications import FakePushSender
from app.services.payments import FakePaymentProvider
from app.services.pubsub import InMemoryPubSub
from app.services.ratelimit import InMemoryRateLimiter
from app.services.transcription import FakeTranscriber
from app.services.usage import InMemoryUsageCounter
from app.services.vector import InMemoryVectorIndex


def enable_sqlite_foreign_keys(engine) -> None:
    """SQLite ignores foreign keys unless asked.

    Without this, ON DELETE CASCADE and SET NULL silently do nothing in tests
    while Postgres enforces them in production — so the suite would pass on
    exactly the referential behaviour most likely to be wrong.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class FakeAppleVerifier:
    def __init__(self):
        self.identity = AppleIdentity(apple_user_id="apple-sub-1", email="apple@example.com")

    def verify(self, identity_token: str) -> AppleIdentity:
        if identity_token != "valid-apple-token":
            from app.services.apple import AppleVerificationError

            raise AppleVerificationError("bad token")
        return self.identity


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret="test-secret-0123456789abcdef0123456789abcdef",
        llm_provider="fake",
        embedding_provider="fake",
        vector_backend="memory",
        pubsub_backend="memory",
        rate_limit_backend="memory",
        usage_counter_backend="memory",
        payment_provider="fake",
        push_backend="fake",
        transcription_provider="fake",
        login_rate_limit=50,
        database_url="sqlite+aiosqlite://",
    )


@pytest.fixture
def fake_chat() -> FakeChatModel:
    return FakeChatModel()


@pytest.fixture
def vector_index() -> InMemoryVectorIndex:
    return InMemoryVectorIndex()


@pytest.fixture
def push_sender() -> FakePushSender:
    return FakePushSender()


@pytest.fixture
def payment_provider() -> FakePaymentProvider:
    return FakePaymentProvider()


@pytest.fixture
def transcriber() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture
def github_client() -> FakeGitHubClient:
    return FakeGitHubClient(
        {
            "octospecialist": [
                Repository(
                    name="fabric-migrator",
                    description="Tooling for Microsoft Fabric migrations",
                    language="Python",
                    stars=120,
                    is_fork=False,
                    size_kb=4200,
                    pushed_at="2026-07-01T10:00:00Z",
                    topics=["microsoft-fabric", "etl"],
                ),
                Repository(
                    name="awesome-list-fork",
                    description="A fork",
                    language="Markdown",
                    stars=0,
                    is_fork=True,
                    size_kb=10,
                    pushed_at="2024-01-01T10:00:00Z",
                    topics=[],
                ),
            ],
            "emptyuser": [
                Repository(
                    name="only-a-fork",
                    description=None,
                    language=None,
                    stars=0,
                    is_fork=True,
                    size_kb=5,
                    pushed_at=None,
                    topics=[],
                )
            ],
        }
    )


@pytest.fixture
async def client(
    test_settings,
    fake_chat,
    vector_index,
    github_client,
    payment_provider,
    push_sender,
    transcriber,
) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite://")
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app(
        test_settings,
        chat_model=fake_chat,
        embedding_model=FakeEmbeddingModel(),
        vector_index=vector_index,
        apple_verifier=FakeAppleVerifier(),
        pubsub=InMemoryPubSub(),
        rate_limiter=InMemoryRateLimiter(),
        github_client=github_client,
        usage_counter=InMemoryUsageCounter(),
        payment_provider=payment_provider,
        push_sender=push_sender,
        transcriber=transcriber,
        sessionmaker=sessionmaker,
    )

    async def override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http_client:
        yield http_client
    await engine.dispose()


def make_requirements(**overrides) -> AssignmentRequirements:
    defaults = dict(
        summary="Migrate an on-prem data warehouse to Microsoft Fabric within six months.",
        roles=[
            RoleRequirement(
                title="Microsoft Fabric Architect",
                count=2,
                seniority="senior",
                must_have_skills=["microsoft fabric", "azure", "data warehousing"],
                nice_to_have_skills=["power bi"],
            )
        ],
        languages=["en"],
        country="NL",
        remote_allowed=True,
        budget=BudgetRange(min_hourly=90, max_hourly=130, currency="EUR"),
        clarifying_questions=["What is the current data warehouse platform?"],
    )
    defaults.update(overrides)
    return AssignmentRequirements(**defaults)


async def register(client: AsyncClient, *, email: str, role: str, name: str = "Test User") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "s3cure-password", "full_name": name, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(token_payload: dict) -> dict:
    return {"Authorization": f"Bearer {token_payload['access_token']}"}


async def create_specialist(
    client: AsyncClient,
    *,
    email: str | None = None,
    skills: list[dict] | None = None,
    hourly_rate: float = 110,
    languages: list[str] | None = None,
) -> tuple[dict, dict]:
    email = email or f"spec-{uuid.uuid4().hex[:8]}@example.com"
    tokens = await register(client, email=email, role="freelancer")
    response = await client.put(
        "/api/v1/specialists/me",
        headers=auth_headers(tokens),
        json={
            "headline": "Azure & Fabric data architect",
            "bio": "Ten years designing cloud data platforms.",
            "skills": skills
            or [
                {"name": "microsoft fabric", "level": 9, "years": 3},
                {"name": "azure", "level": 9, "years": 8},
                {"name": "data warehousing", "level": 8, "years": 10},
            ],
            "languages": languages or ["en", "nl"],
            "years_experience": 10,
            "hourly_rate": hourly_rate,
        },
    )
    assert response.status_code == 200, response.text
    return tokens, response.json()


async def create_company(client: AsyncClient, *, email: str = "hm@example.com") -> dict:
    tokens = await register(client, email=email, role="hiring_manager")
    response = await client.put(
        "/api/v1/companies/me",
        headers=auth_headers(tokens),
        json={"name": "Acme BV", "industry": "logistics", "country": "NL"},
    )
    assert response.status_code == 200, response.text
    return tokens
