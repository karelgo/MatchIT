"""Every timestamp the API emits must be tz-aware UTC.

SQLite (tests) drops tzinfo where Postgres preserves it, so without an explicit
boundary normalisation the same endpoint returns different shapes per backend and
clients are left guessing the zone.
"""

import json
from datetime import UTC, datetime

from app.schemas.api import ConversationResponse, MessageResponse, _as_utc
from tests.conftest import auth_headers
from tests.test_chat import make_mutual_match

ISO_WITH_ZONE_SUFFIXES = ("Z", "+00:00")


def test_as_utc_attaches_and_converts():
    naive = datetime(2026, 7, 27, 9, 25, 29, 693691)
    assert _as_utc(naive).tzinfo is UTC

    from datetime import timedelta, timezone

    amsterdam = datetime(2026, 7, 27, 11, 0, tzinfo=timezone(timedelta(hours=2)))
    converted = _as_utc(amsterdam)
    assert converted.utcoffset().total_seconds() == 0
    assert converted.hour == 9


def test_response_models_reject_naive_leakage():
    import uuid

    naive = datetime(2026, 7, 27, 9, 25, 29, 693691)
    message = MessageResponse(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        sender_name="S",
        content="hi",
        created_at=naive,
    )
    assert message.created_at.tzinfo is not None
    serialised = json.loads(message.model_dump_json())["created_at"]
    assert serialised.endswith(ISO_WITH_ZONE_SUFFIXES), serialised

    conversation = ConversationResponse(
        id=uuid.uuid4(),
        match_id=uuid.uuid4(),
        counterpart_name="Acme",
        assignment_title="Architect",
        last_message=None,
        last_message_at=None,
        created_at=naive,
    )
    assert conversation.created_at.tzinfo is not None


async def test_api_timestamps_all_carry_a_timezone(client, fake_chat):
    """End to end over SQLite, the backend that loses tzinfo."""
    specialist_tokens, company_tokens, _ = await make_mutual_match(
        client, fake_chat, company_email="ts-hm@example.com"
    )
    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]
    await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_headers(company_tokens),
        json={"content": "when can you start?"},
    )

    payloads = {
        "user": (await client.get("/api/v1/users/me", headers=auth_headers(company_tokens))).json(),
        "assignments": (
            await client.get("/api/v1/assignments", headers=auth_headers(company_tokens))
        ).json()[0],
        "conversation": (
            await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
        ).json()[0],
        "message": (
            await client.get(
                f"/api/v1/conversations/{conversation['id']}/messages",
                headers=auth_headers(company_tokens),
            )
        ).json()[0],
    }

    checked = 0
    for name, payload in payloads.items():
        for field, value in payload.items():
            if field.endswith("_at") and isinstance(value, str):
                assert value.endswith(ISO_WITH_ZONE_SUFFIXES), (
                    f"{name}.{field} has no timezone: {value!r}"
                )
                checked += 1
    assert checked >= 4, f"expected several timestamps to check, saw {checked}"
