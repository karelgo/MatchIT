"""WebSocket chat round-trip.

Starlette's TestClient drives the ASGI app from worker threads with their own
event loops, so this test builds its own app around a file-backed SQLite database
(NullPool: no cross-loop connection reuse) instead of the shared async fixtures.
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.ai.embeddings import FakeEmbeddingModel
from app.ai.llm import FakeChatModel
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.pubsub import InMemoryPubSub
from app.services.vector import InMemoryVectorIndex
from tests.conftest import FakeAppleVerifier, make_requirements


def build_sync_client(tmp_path) -> TestClient:
    from tests.conftest import Settings

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/chat.db", poolclass=NullPool
    )

    async def create_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    settings = Settings(
        jwt_secret="test-secret-0123456789abcdef0123456789abcdef",
        llm_provider="fake",
        embedding_provider="fake",
        vector_backend="memory",
        pubsub_backend="memory",
        rate_limit_backend="memory",
        login_rate_limit=200,
    )
    app = create_app(
        settings,
        chat_model=FakeChatModel([make_requirements()]),
        embedding_model=FakeEmbeddingModel(),
        vector_index=InMemoryVectorIndex(),
        apple_verifier=FakeAppleVerifier(),
        pubsub=InMemoryPubSub(),
        sessionmaker=sessionmaker,
    )

    async def override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def register(client: TestClient, email: str, role: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "s3cure-password", "full_name": "WS User", "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_websocket_chat_roundtrip(tmp_path):
    client = build_sync_client(tmp_path)

    specialist = register(client, "ws-spec@example.com", "freelancer")
    assert (
        client.put(
            "/api/v1/specialists/me",
            headers=headers(specialist),
            json={
                "headline": "Fabric architect",
                "skills": [{"name": "microsoft fabric", "level": 9, "years": 3}],
                "hourly_rate": 110,
            },
        ).status_code
        == 200
    )
    company = register(client, "ws-hm@example.com", "hiring_manager")
    assert (
        client.put(
            "/api/v1/companies/me", headers=headers(company), json={"name": "Acme BV"}
        ).status_code
        == 200
    )

    assignment = client.post(
        "/api/v1/assignments",
        headers=headers(company),
        json={"description": "We need a Fabric architect to migrate our data warehouse soon."},
    ).json()
    match = client.post(
        f"/api/v1/assignments/{assignment['id']}/matches", headers=headers(company)
    ).json()[0]
    client.post(
        f"/api/v1/matches/{match['id']}/decision",
        headers=headers(specialist),
        json={"decision": "accepted"},
    )
    client.post(
        f"/api/v1/matches/{match['id']}/decision",
        headers=headers(company),
        json={"decision": "accepted"},
    )
    conversation = client.get("/api/v1/conversations", headers=headers(company)).json()[0]

    ws_path = f"/api/v1/ws/conversations/{conversation['id']}"
    with (
        client.websocket_connect(f"{ws_path}?token={specialist['access_token']}") as ws_spec,
        client.websocket_connect(f"{ws_path}?token={company['access_token']}") as ws_company,
    ):
        ws_spec.send_json({"content": "Hello from the specialist!"})
        received_by_company = ws_company.receive_json()
        echoed_to_specialist = ws_spec.receive_json()
        assert received_by_company["content"] == "Hello from the specialist!"
        assert echoed_to_specialist["id"] == received_by_company["id"]
        assert received_by_company["sender_name"] == "WS User"

        # a REST-posted message is broadcast to live sockets too
        client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=headers(company),
            json={"content": "Great, when can you start?"},
        )
        assert ws_spec.receive_json()["content"] == "Great, when can you start?"
        assert ws_company.receive_json()["content"] == "Great, when can you start?"

    # both messages were persisted
    messages = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages", headers=headers(company)
    ).json()
    assert [m["content"] for m in messages] == [
        "Hello from the specialist!",
        "Great, when can you start?",
    ]


def test_websocket_rejects_bad_token_and_foreign_conversation(tmp_path):
    client = build_sync_client(tmp_path)
    specialist = register(client, "ws-auth-spec@example.com", "freelancer")

    # invalid token: closed with 4401 before accept
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/api/v1/ws/conversations/00000000-0000-0000-0000-000000000000?token=forged"
        ):
            pass
    assert excinfo.value.code == 4401

    # valid token, nonexistent/foreign conversation: 4404
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/api/v1/ws/conversations/00000000-0000-0000-0000-000000000000"
            f"?token={specialist['access_token']}"
        ):
            pass
    assert excinfo.value.code == 4404
