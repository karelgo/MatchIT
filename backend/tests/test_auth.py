from tests.conftest import auth_headers, register


async def test_register_login_me_flow(client):
    tokens = await register(client, email="anna@example.com", role="freelancer", name="Anna")
    assert tokens["user"]["email"] == "anna@example.com"
    assert tokens["user"]["role"] == "freelancer"

    me = await client.get("/api/v1/users/me", headers=auth_headers(tokens))
    assert me.status_code == 200
    assert me.json()["full_name"] == "Anna"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "Anna@Example.com", "password": "s3cure-password"},
    )
    assert login.status_code == 200


async def test_duplicate_email_conflict(client):
    await register(client, email="dup@example.com", role="freelancer")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "s3cure-password",
            "full_name": "Dup",
            "role": "freelancer",
        },
    )
    assert response.status_code == 409


async def test_wrong_password_rejected(client):
    await register(client, email="bob@example.com", role="hiring_manager")
    response = await client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "wrong-password!"}
    )
    assert response.status_code == 401


async def test_refresh_rotation_revokes_old_token(client):
    tokens = await register(client, email="rot@example.com", role="freelancer")

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200
    rotated = first.json()

    # the original refresh token was rotated out and must now fail
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    # the rotated token works
    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert second.status_code == 200


async def test_logout_revokes_refresh_token(client):
    tokens = await register(client, email="out@example.com", role="freelancer")
    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout.status_code == 204
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


async def test_apple_sign_in_creates_and_reuses_account(client):
    first = await client.post(
        "/api/v1/auth/apple",
        json={"identity_token": "valid-apple-token", "full_name": "Apple Anna"},
    )
    assert first.status_code == 200
    assert first.json()["user"]["email"] == "apple@example.com"

    second = await client.post("/api/v1/auth/apple", json={"identity_token": "valid-apple-token"})
    assert second.status_code == 200
    assert second.json()["user"]["id"] == first.json()["user"]["id"]

    bad = await client.post("/api/v1/auth/apple", json={"identity_token": "forged"})
    assert bad.status_code == 401


async def test_missing_token_unauthorized(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
