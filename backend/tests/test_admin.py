from sqlalchemy import select

from app.models import User, UserRole
from tests.conftest import auth_headers, create_company, create_specialist, register
from tests.test_chat import make_mutual_match
from tests.test_contracts import TERMS, draft_of


async def make_admin(client, *, email: str = "admin@example.com") -> dict:
    """Admins cannot be registered publicly, so promote one directly."""
    await register(client, email=email, role="hiring_manager")
    sessionmaker = client._transport.app.state.sessionmaker
    async with sessionmaker() as db:
        user = await db.scalar(select(User).where(User.email == email))
        user.role = UserRole.ADMIN
        await db.commit()
    # re-login so the token carries the new role claim
    refreshed = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "s3cure-password"}
    )
    return refreshed.json()


# ---- privilege escalation ----


async def test_admin_role_cannot_be_self_assigned(client):
    """Public sign-up must never mint privilege."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wannabe@example.com",
            "password": "s3cure-password",
            "full_name": "Wannabe",
            "role": "admin",
        },
    )
    assert response.status_code == 403

    sessionmaker = client._transport.app.state.sessionmaker
    async with sessionmaker() as db:
        assert await db.scalar(select(User).where(User.email == "wannabe@example.com")) is None


async def test_apple_sign_in_cannot_mint_an_admin(client):
    response = await client.post(
        "/api/v1/auth/apple",
        json={"identity_token": "valid-apple-token", "full_name": "A", "role": "admin"},
    )
    assert response.status_code == 403


async def test_admin_surface_is_invisible_to_normal_users(client):
    tokens, _ = await create_specialist(client, email="nosy@example.com")
    for path in ("/api/v1/admin/metrics", "/api/v1/admin/users", "/api/v1/admin/audit"):
        response = await client.get(path, headers=auth_headers(tokens))
        # 404 rather than 403: the admin surface should not confirm it exists
        assert response.status_code == 404, path


async def test_admin_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/admin/metrics")).status_code == 401


# ---- metrics ----


async def test_metrics_report_the_funnel_and_ai_usage(client, fake_chat):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="metrics-hm@example.com"
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

    admin = await make_admin(client)
    body = (await client.get("/api/v1/admin/metrics", headers=auth_headers(admin))).json()

    funnel = body["funnel"]
    assert funnel["specialists"] >= 1
    assert funnel["companies"] >= 1
    assert funnel["assignments"] >= 1
    assert funnel["matches_mutual"] >= 1
    assert funnel["contracts_active"] == 1

    assert 0.0 <= body["conversion"]["suggested_to_mutual"] <= 1.0
    assert body["conversion"]["mutual_to_contracted"] > 0
    assert body["quality"]["average_match_score"] > 0
    assert body["users_by_role"]["freelancer"] >= 1
    assert body["mean_time_to_contract_hours"] is not None

    # AI usage is attributed per feature, not lumped together
    usage = body["ai_calls_by_feature"]
    assert usage["intake"] >= 1
    assert usage["contract"] >= 1
    assert "interview" not in usage or usage["interview"] == 0


async def test_metrics_on_an_empty_platform_do_not_divide_by_zero(client):
    admin = await make_admin(client, email="empty-admin@example.com")
    body = (await client.get("/api/v1/admin/metrics", headers=auth_headers(admin))).json()
    assert body["funnel"]["assignments"] == 0
    assert all(rate == 0.0 for rate in body["conversion"].values())
    assert body["mean_time_to_contract_hours"] is None


# ---- user management ----


async def test_suspend_and_reinstate_a_user(client):
    victim, _ = await create_specialist(client, email="suspendme@example.com")
    admin = await make_admin(client, email="admin2@example.com")

    users = (
        await client.get(
            "/api/v1/admin/users", headers=auth_headers(admin), params={"role": "freelancer"}
        )
    ).json()
    target = next(u for u in users if u["email"] == "suspendme@example.com")
    assert target["is_active"] is True

    suspended = await client.post(
        f"/api/v1/admin/users/{target['id']}/suspend", headers=auth_headers(admin)
    )
    assert suspended.status_code == 200
    assert suspended.json()["is_active"] is False

    # a suspended user is locked out immediately, on an already-issued token
    assert (
        await client.get("/api/v1/users/me", headers=auth_headers(victim))
    ).status_code == 401

    reinstated = await client.post(
        f"/api/v1/admin/users/{target['id']}/reinstate", headers=auth_headers(admin)
    )
    assert reinstated.status_code == 200
    assert reinstated.json()["is_active"] is True
    assert (
        await client.get("/api/v1/users/me", headers=auth_headers(victim))
    ).status_code == 200


async def test_admin_cannot_suspend_themselves(client):
    admin = await make_admin(client, email="admin3@example.com")
    response = await client.post(
        f"/api/v1/admin/users/{admin['user']['id']}/suspend", headers=auth_headers(admin)
    )
    assert response.status_code == 409


async def test_user_listing_filters_and_paginates(client):
    for index in range(3):
        await create_specialist(client, email=f"page{index}@example.com")
    await create_company(client, email="pagehm@example.com")
    admin = await make_admin(client, email="admin4@example.com")

    freelancers = (
        await client.get(
            "/api/v1/admin/users", headers=auth_headers(admin), params={"role": "freelancer"}
        )
    ).json()
    assert len(freelancers) >= 3
    assert all(u["role"] == "freelancer" for u in freelancers)

    page = (
        await client.get(
            "/api/v1/admin/users", headers=auth_headers(admin), params={"limit": 2, "offset": 0}
        )
    ).json()
    assert len(page) == 2


# ---- audit search ----


async def test_audit_search_filters_by_action(client):
    await create_specialist(client, email="audited2@example.com")
    admin = await make_admin(client, email="admin5@example.com")

    registrations = (
        await client.get(
            "/api/v1/admin/audit",
            headers=auth_headers(admin),
            params={"action": "user_registered"},
        )
    ).json()
    assert registrations
    assert all(entry["action"] == "user_registered" for entry in registrations)
    assert all("created_at" in entry for entry in registrations)


async def test_suspension_is_audited(client):
    victim, _ = await create_specialist(client, email="auditsuspend@example.com")
    admin = await make_admin(client, email="admin6@example.com")
    users = (await client.get("/api/v1/admin/users", headers=auth_headers(admin))).json()
    target = next(u for u in users if u["email"] == "auditsuspend@example.com")
    await client.post(f"/api/v1/admin/users/{target['id']}/suspend", headers=auth_headers(admin))

    entries = (
        await client.get(
            "/api/v1/admin/audit",
            headers=auth_headers(admin),
            params={"action": "user_suspended"},
        )
    ).json()
    assert len(entries) == 1
    assert entries[0]["target_id"] == target["id"]
    assert entries[0]["actor_user_id"] == admin["user"]["id"]
