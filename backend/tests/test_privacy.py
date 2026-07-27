import pytest
from sqlalchemy import func, select

from app.models import AuditAction, AuditLog, Contract, ContractStatus, User
from app.services.ratelimit import InMemoryRateLimiter, RateLimitExceeded
from tests.conftest import auth_headers, create_company, register
from tests.test_chat import make_mutual_match
from tests.test_contracts import TERMS, draft_of

# ---- rate limiting ----


async def test_limiter_allows_up_to_limit_then_blocks():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        await limiter.hit("k", limit=3, window_seconds=60)
    with pytest.raises(RateLimitExceeded) as excinfo:
        await limiter.hit("k", limit=3, window_seconds=60)
    assert excinfo.value.retry_after > 0


async def test_limiter_buckets_are_per_key():
    limiter = InMemoryRateLimiter()
    await limiter.hit("a", limit=1, window_seconds=60)
    await limiter.hit("b", limit=1, window_seconds=60)  # must not be blocked by "a"
    with pytest.raises(RateLimitExceeded):
        await limiter.hit("a", limit=1, window_seconds=60)


async def test_login_endpoint_rate_limits_brute_force(client, test_settings):
    """Password guessing must hit a wall, and the wall must say when to retry."""
    await register(client, email="brute@example.com", role="freelancer")
    seen_429 = False
    for _ in range(test_settings.login_rate_limit + 5):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "brute@example.com", "password": "wrong-password!"},
        )
        if response.status_code == 429:
            seen_429 = True
            assert response.headers.get("Retry-After")
            break
        assert response.status_code == 401
    assert seen_429, "login was never rate limited"


# ---- audit trail ----


async def _audit_actions(client) -> list[str]:
    """Read the audit table through the app's own sessionmaker."""
    sessionmaker = client._transport.app.state.sessionmaker
    async with sessionmaker() as db:
        rows = await db.scalars(select(AuditLog).order_by(AuditLog.created_at))
        return [row.action.value for row in rows]


async def test_register_and_login_are_audited(client):
    tokens = await register(client, email="audited@example.com", role="freelancer")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "audited@example.com", "password": "s3cure-password"},
    )
    await client.post(
        "/api/v1/auth/login", json={"email": "audited@example.com", "password": "nope-wrong-pw"}
    )
    actions = await _audit_actions(client)
    assert AuditAction.USER_REGISTERED.value in actions
    assert AuditAction.LOGIN_SUCCEEDED.value in actions
    assert AuditAction.LOGIN_FAILED.value in actions
    assert tokens["user"]["id"]


async def test_failed_login_never_records_the_password(client):
    await register(client, email="secretpw@example.com", role="freelancer")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "secretpw@example.com", "password": "hunter2-super-secret"},
    )
    sessionmaker = client._transport.app.state.sessionmaker
    async with sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.LOGIN_FAILED)
        )
        for row in rows:
            assert "hunter2-super-secret" not in str(row.context)
            assert row.context.get("email") == "secretpw@example.com"


# ---- GDPR export ----


async def test_export_returns_the_users_own_data(client, fake_chat):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="gdpr-hm@example.com"
    )
    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]
    await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(specialist_tokens),
        json={"content": "my message content"},
    )

    export = await client.get("/api/v1/users/me/export", headers=auth_headers(specialist_tokens))
    assert export.status_code == 200, export.text
    data = export.json()
    assert data["account"]["email"]
    assert data["specialist_profile"]["headline"]
    assert data["matches"], "the specialist's matches belong in their export"
    assert any(m["content"] == "my message content" for m in data["messages"])
    # the company's private data is not the specialist's to receive
    assert "company_profile" not in data
    assert "assignments" not in data

    company_export = (
        await client.get("/api/v1/users/me/export", headers=auth_headers(company_tokens))
    ).json()
    assert company_export["company_profile"]["name"] == "Acme BV"
    assert company_export["assignments"]
    assert "specialist_profile" not in company_export

    actions = await _audit_actions(client)
    assert AuditAction.DATA_EXPORTED.value in actions


async def test_export_requires_authentication(client):
    assert (await client.get("/api/v1/users/me/export")).status_code == 401


# ---- GDPR erasure ----


async def test_erasure_deletes_the_account_and_keeps_the_audit_trail(client):
    tokens = await register(client, email="erase@example.com", role="freelancer")
    user_id = tokens["user"]["id"]

    deleted = await client.delete("/api/v1/users/me", headers=auth_headers(tokens))
    assert deleted.status_code == 204

    # the account is gone
    assert (await client.get("/api/v1/users/me", headers=auth_headers(tokens))).status_code == 401
    sessionmaker = client._transport.app.state.sessionmaker
    async with sessionmaker() as db:
        remaining = await db.scalar(
            select(func.count()).select_from(User).where(User.email == "erase@example.com")
        )
        assert remaining == 0
        # the audit entries survive, with the actor reference nulled
        count = await db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.ACCOUNT_DELETED)
        )
        assert count == 1
        dangling = await db.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.ACCOUNT_DELETED)
        )
        for row in dangling:
            assert row.actor_user_id is None, "actor FK must be SET NULL, not cascade-deleted"
    assert user_id


async def test_erasure_blocked_while_a_contract_is_active(client, fake_chat):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="gdpr-live@example.com"
    )
    fake_chat.responses.append(draft_of())
    await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json=TERMS,
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(specialist_tokens)
    )

    for tokens in (specialist_tokens, company_tokens):
        blocked = await client.delete("/api/v1/users/me", headers=auth_headers(tokens))
        assert blocked.status_code == 409
        assert "active contract" in blocked.json()["detail"]

    # once the engagement ends, erasure proceeds
    sessionmaker = client._transport.app.state.sessionmaker
    async with sessionmaker() as db:
        contract = await db.scalar(select(Contract))
        contract.status = ContractStatus.COMPLETED
        await db.commit()

    assert (
        await client.delete("/api/v1/users/me", headers=auth_headers(specialist_tokens))
    ).status_code == 204


async def test_erasure_requires_authentication(client):
    assert (await client.delete("/api/v1/users/me")).status_code == 401
    await create_company(client, email="still-here@example.com")
