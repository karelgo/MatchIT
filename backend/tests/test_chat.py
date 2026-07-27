from httpx import AsyncClient

from tests.conftest import auth_headers, create_company, create_specialist, make_requirements

DESCRIPTION = (
    "We need two Microsoft Fabric architects to migrate our on-prem data warehouse "
    "to Fabric within six months. Start early August, mostly remote, Dutch team."
)


async def make_mutual_match(
    client: AsyncClient, fake_chat, *, company_email: str = "chat-hm@example.com"
) -> tuple[dict, dict, dict]:
    """Returns (specialist_tokens, company_tokens, mutual match payload)."""
    specialist_tokens, _ = await create_specialist(client)
    company_tokens = await create_company(client, email=company_email)
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
    await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(specialist_tokens),
        json={"decision": "accepted"},
    )
    final = await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(company_tokens),
        json={"decision": "accepted"},
    )
    assert final.json()["status"] == "mutual"
    return specialist_tokens, company_tokens, final.json()


async def test_mutual_match_opens_conversation_for_both_parties(client, fake_chat):
    specialist_tokens, company_tokens, match = await make_mutual_match(client, fake_chat)

    specialist_view = (
        await client.get("/api/v1/conversations", headers=auth_headers(specialist_tokens))
    ).json()
    company_view = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()

    assert len(specialist_view) == 1
    assert len(company_view) == 1
    assert specialist_view[0]["id"] == company_view[0]["id"]
    assert specialist_view[0]["match_id"] == match["id"]
    # each side sees the other party's name
    assert specialist_view[0]["counterpart_name"] == "Acme BV"
    assert company_view[0]["counterpart_name"] == "Test User"
    assert specialist_view[0]["assignment_title"] == "Microsoft Fabric Architect"
    assert specialist_view[0]["last_message"] is None


async def test_send_and_read_messages(client, fake_chat):
    specialist_tokens, company_tokens, _ = await make_mutual_match(
        client, fake_chat, company_email="chat-hm2@example.com"
    )
    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]

    sent = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(company_tokens),
        json={"content": "Hi! Can you start on the first Monday of September?"},
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["sender_name"] == "Test User"

    reply = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(specialist_tokens),
        json={"content": "Yes — September 7 works."},
    )
    assert reply.status_code == 201

    messages = (
        await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=auth_headers(specialist_tokens),
        )
    ).json()
    assert [m["content"] for m in messages] == [
        "Hi! Can you start on the first Monday of September?",
        "Yes — September 7 works.",
    ]

    # the conversation list surfaces the last message
    refreshed = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]
    assert refreshed["last_message"] == "Yes — September 7 works."


async def test_blank_messages_rejected(client, fake_chat):
    """min_length alone would let "   " through and store an empty message."""
    _, company_tokens, _ = await make_mutual_match(
        client, fake_chat, company_email="chat-blank@example.com"
    )
    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]

    for blank in ("", "   ", "\n\t "):
        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=auth_headers(company_tokens),
            json={"content": blank},
        )
        assert response.status_code == 422, f"{blank!r} was accepted"

    # surrounding whitespace on a real message is trimmed, not rejected
    ok = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(company_tokens),
        json={"content": "  hello  "},
    )
    assert ok.status_code == 201
    assert ok.json()["content"] == "hello"


async def test_outsider_cannot_access_conversation(client, fake_chat):
    _, company_tokens, _ = await make_mutual_match(
        client, fake_chat, company_email="chat-hm3@example.com"
    )
    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]

    outsider_tokens = await create_company(client, email="chat-outsider@example.com")
    read = await client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(outsider_tokens),
    )
    assert read.status_code == 404
    write = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(outsider_tokens),
        json={"content": "let me in"},
    )
    assert write.status_code == 404
    assert (
        await client.get("/api/v1/conversations", headers=auth_headers(outsider_tokens))
    ).json() == []


async def test_double_accept_does_not_duplicate_conversation(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="chat-hm4@example.com"
    )
    # company re-sends its accept decision after the match is already mutual
    again = await client.post(
        f"/api/v1/matches/{match['id']}/decision",
        headers=auth_headers(company_tokens),
        json={"decision": "accepted"},
    )
    assert again.status_code == 200
    conversations = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()
    assert len(conversations) == 1
