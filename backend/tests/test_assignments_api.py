from tests.conftest import auth_headers, create_company, create_specialist, make_requirements

DESCRIPTION = (
    "We need two Microsoft Fabric architects to migrate our on-prem data warehouse "
    "to Fabric within six months. Start early August, mostly remote, Dutch team."
)


async def test_full_hiring_loop(client, fake_chat, vector_index):
    """Company describes problem -> AI extracts -> matches ranked -> mutual match."""
    specialist_tokens, specialist_profile = await create_specialist(client)
    await create_specialist(
        client, skills=[{"name": "react", "level": 9, "years": 6}], hourly_rate=80
    )
    company_tokens = await create_company(client)

    fake_chat.responses.append(make_requirements())
    created = await client.post(
        "/api/v1/assignments",
        headers=auth_headers(company_tokens),
        json={"description": DESCRIPTION},
    )
    assert created.status_code == 201, created.text
    assignment = created.json()
    assert assignment["status"] == "open"
    assert assignment["requirements"]["roles"][0]["title"] == "Microsoft Fabric Architect"
    assert assignment["requirements"]["clarifying_questions"]
    # the intake prompt received the company's own words
    assert DESCRIPTION[:40] in fake_chat.calls[0]["user"]

    generated = await client.post(
        f"/api/v1/assignments/{assignment['id']}/matches", headers=auth_headers(company_tokens)
    )
    assert generated.status_code == 200, generated.text
    matches = generated.json()
    assert len(matches) == 2
    assert matches[0]["specialist_id"] == specialist_profile["id"]
    assert matches[0]["score"] > matches[1]["score"]
    assert "skills" in matches[0]["breakdown"]

    # specialist sees the opportunity and accepts
    inbox = await client.get("/api/v1/matches/inbox", headers=auth_headers(specialist_tokens))
    assert inbox.status_code == 200
    assert any(m["id"] == matches[0]["id"] for m in inbox.json())

    accept_specialist = await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(specialist_tokens),
        json={"decision": "accepted"},
    )
    assert accept_specialist.status_code == 200
    assert accept_specialist.json()["status"] == "suggested"

    # company accepts -> mutual match
    accept_company = await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(company_tokens),
        json={"decision": "accepted"},
    )
    assert accept_company.status_code == 200
    assert accept_company.json()["status"] == "mutual"


async def test_rejection_closes_match(client, fake_chat):
    specialist_tokens, _ = await create_specialist(client)
    company_tokens = await create_company(client, email="hm2@example.com")

    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    matches = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()

    rejected = await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(specialist_tokens),
        json={"decision": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "closed"


async def test_specialist_cannot_create_assignment(client):
    specialist_tokens, _ = await create_specialist(client)
    response = await client.post(
        "/api/v1/assignments",
        headers=auth_headers(specialist_tokens),
        json={"description": DESCRIPTION},
    )
    assert response.status_code == 403


async def test_company_cannot_see_foreign_assignment(client, fake_chat):
    owner_tokens = await create_company(client, email="owner@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(owner_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()

    other_tokens = await create_company(client, email="other@example.com")
    response = await client.get(
        f"/api/v1/assignments/{assignment['id']}", headers=auth_headers(other_tokens)
    )
    assert response.status_code == 404


async def test_outsider_cannot_decide_match(client, fake_chat):
    await create_specialist(client)
    company_tokens = await create_company(client, email="hm3@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    matches = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()

    outsider_tokens = await create_company(client, email="outsider@example.com")
    response = await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(outsider_tokens),
        json={"decision": "accepted"},
    )
    assert response.status_code == 403
