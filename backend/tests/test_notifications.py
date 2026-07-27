import pytest

from app.services.notifications import FakePushSender, PushMessage
from app.services.notifier import Notifier
from tests.conftest import auth_headers, create_company, create_specialist, register
from tests.test_chat import make_mutual_match
from tests.test_contracts import TERMS, draft_of

DEVICE = {"token": "a" * 64}


async def register_device(client, tokens, token: str = "a" * 64):
    response = await client.post(
        "/api/v1/users/me/devices", headers=auth_headers(tokens), json={"token": token}
    )
    assert response.status_code == 204, response.text


# ---- delivery is best-effort ----


async def test_a_failing_push_never_raises():
    """A push failure must not fail the action that triggered it."""

    class ExplodingSender:
        async def send(self, message, tokens):
            raise RuntimeError("APNs is down")

    notifier = Notifier(ExplodingSender())

    class FakeDb:
        async def scalars(self, _statement):
            return ["token-1"]

    import uuid

    # must not raise
    await notifier.notify(
        FakeDb(), uuid.uuid4(), title="t", body="b", data={}
    )


async def test_no_tokens_means_no_send():
    sender = FakePushSender()
    notifier = Notifier(sender)

    class EmptyDb:
        async def scalars(self, _statement):
            return []

    import uuid

    await notifier.notify(EmptyDb(), uuid.uuid4(), title="t", body="b", data={})
    assert sender.sent == []


# ---- device registration ----


async def test_device_token_follows_the_device_to_a_new_user(client):
    """The same handset registering under a new account must stop notifying the old one."""
    first, _ = await create_specialist(client, email="dev1@example.com")
    second, _ = await create_specialist(client, email="dev2@example.com")

    await register_device(client, first)
    await register_device(client, second)  # same token, different user

    sessionmaker = client._transport.app.state.sessionmaker
    from sqlalchemy import func, select

    from app.models import DeviceToken

    async with sessionmaker() as db:
        rows = list(await db.scalars(select(DeviceToken)))
        assert len(rows) == 1, "the token must move, not duplicate"
        assert str(rows[0].user_id) == second["user"]["id"]
        assert await db.scalar(select(func.count()).select_from(DeviceToken)) == 1


async def test_device_registration_requires_authentication(client):
    assert (await client.post("/api/v1/users/me/devices", json=DEVICE)).status_code == 401


@pytest.mark.parametrize("bad_token", ["", "   ", "short"])
async def test_invalid_device_tokens_are_rejected(client, bad_token):
    tokens = await register(client, email=f"badtok{len(bad_token)}@example.com", role="freelancer")
    response = await client.post(
        "/api/v1/users/me/devices", headers=auth_headers(tokens), json={"token": bad_token}
    )
    assert response.status_code == 422


# ---- triggers ----


async def test_both_parties_are_notified_on_a_mutual_match(client, fake_chat, push_sender):
    specialist_tokens, _ = await create_specialist(client, email="notif-spec@example.com")
    await register_device(client, specialist_tokens, token="s" * 64)
    company_tokens = await create_company(client, email="notif-hm@example.com")
    await register_device(client, company_tokens, token="c" * 64)

    from tests.conftest import make_requirements
    from tests.test_chat import DESCRIPTION

    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    match = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()[0]

    await client.post(
        f"/api/v1/matches/{match['id']}/decision",
        headers=auth_headers(specialist_tokens),
        json={"decision": "accepted"},
    )
    assert push_sender.sent == [], "no push until the match is actually mutual"

    await client.post(
        f"/api/v1/matches/{match['id']}/decision",
        headers=auth_headers(company_tokens),
        json={"decision": "accepted"},
    )
    titles = [message.title for message, _ in push_sender.sent]
    assert titles.count("It's a match") == 2, "both parties must be told"
    recipients = {str(message.user_id) for message, _ in push_sender.sent}
    assert len(recipients) == 2


async def test_only_the_recipient_is_notified_of_a_message(client, fake_chat, push_sender):
    specialist_tokens, company_tokens, _ = await make_mutual_match(
        client, fake_chat, company_email="notif-msg@example.com"
    )
    await register_device(client, specialist_tokens, token="s" * 64)
    await register_device(client, company_tokens, token="c" * 64)
    push_sender.sent.clear()

    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]
    await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(company_tokens),
        json={"content": "Can you start in September?"},
    )

    assert len(push_sender.sent) == 1, "the sender must not be notified of their own message"
    message, tokens = push_sender.sent[0]
    assert message.body == "Can you start in September?"
    assert message.data["type"] == "message"
    assert tokens == ["s" * 64]


async def test_contract_signature_notifies_the_counterparty(client, fake_chat, push_sender):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="notif-ct@example.com"
    )
    await register_device(client, specialist_tokens, token="s" * 64)
    await register_device(client, company_tokens, token="c" * 64)
    fake_chat.responses.append(draft_of())
    await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json=TERMS,
    )
    push_sender.sent.clear()

    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    first, _ = push_sender.sent[-1]
    assert first.title == "Signature received"

    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(specialist_tokens)
    )
    final, _ = push_sender.sent[-1]
    assert final.title == "Contract signed"
    assert "active" in final.body


def test_push_message_carries_routing_data():
    message = PushMessage(
        user_id=__import__("uuid").uuid4(), title="t", body="b", data={"type": "message"}
    )
    assert message.data["type"] == "message"
