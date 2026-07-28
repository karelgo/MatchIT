"""AI transparency reports: content, gating, signature."""

import copy

import pytest

from app.services.transparency import TransparencyService, specialist_reference
from tests.conftest import auth_headers, create_company, create_specialist, make_requirements
from tests.test_admin import make_admin
from tests.test_chat import DESCRIPTION, make_mutual_match
from tests.test_interviews import answer_all, assessment_of, plan_of


async def _report(client, tokens, match_id) -> dict:
    response = await client.get(
        f"/api/v1/matches/{match_id}/transparency-report", headers=auth_headers(tokens)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_report_explains_the_ranking_with_weighted_contributions(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-hm@example.com"
    )
    body = await _report(client, company_tokens, match["id"])
    ranking = body["report"]["ranking"]

    assert ranking["candidates_scored"] == 1
    assert ranking["rank"] == 1
    components = {c["component"]: c for c in ranking["components"]}
    assert set(components) == {
        "skills",
        "semantic",
        "rate",
        "availability",
        "location",
        "language",
    }
    # Every contribution is its weight times its score, and they sum to the total.
    for component in components.values():
        assert component["contribution"] == pytest.approx(
            component["weight"] * component["score"], abs=1e-4
        )
    total = sum(c["contribution"] for c in components.values())
    assert total == pytest.approx(ranking["total_score"], abs=1e-3)


async def test_report_is_refused_until_the_company_has_decided(client, fake_chat):
    specialist_tokens, _ = await create_specialist(client, email="tr-pending@example.com")
    company_tokens = await create_company(client, email="tr-pending-hm@example.com")
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

    for tokens in (company_tokens, specialist_tokens):
        response = await client.get(
            f"/api/v1/matches/{matches[0]['id']}/transparency-report",
            headers=auth_headers(tokens),
        )
        assert response.status_code == 409, response.text
        assert "decided" in response.json()["detail"]


async def test_a_rejected_candidate_still_gets_the_report(client, fake_chat):
    """The rejection is exactly the decision most worth being able to see."""
    specialist_tokens, _ = await create_specialist(client, email="tr-rej@example.com")
    company_tokens = await create_company(client, email="tr-rej-hm@example.com")
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
        headers=auth_headers(company_tokens),
        json={"decision": "rejected"},
    )

    body = await _report(client, specialist_tokens, matches[0]["id"])
    decisions = {entry["party"]: entry for entry in body["report"]["decisions"]}
    assert decisions["company"]["decision"] == "rejected"
    assert decisions["company"]["decided_at"] is not None
    assert decisions["company"]["made_by"] == "a person"
    assert decisions["specialist"]["decision"] == "pending"


async def test_both_parties_receive_the_identical_document(client, fake_chat):
    """A shared signature is only meaningful over a shared document."""
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-same@example.com"
    )
    fake_chat.responses.append(plan_of())
    await client.post(
        f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
    )
    await answer_all(
        client,
        fake_chat,
        specialist_tokens,
        match["id"],
        answers=["I migrated a 40TB warehouse to Fabric over nine months."],
        assessment=assessment_of(0.82),
    )

    company_view = await _report(client, company_tokens, match["id"])
    specialist_view = await _report(client, specialist_tokens, match["id"])
    assert company_view["report"] == specialist_view["report"]
    # including the hiring-manager-facing conclusions, which the live interview
    # projection withholds but a decision record must not
    interview = specialist_view["report"]["interview"]
    assert interview["recommendation"] == "yes"
    assert interview["concerns"]


async def test_report_carries_interview_rationale_and_scores(client, fake_chat):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-int@example.com"
    )
    fake_chat.responses.append(plan_of())
    await client.post(
        f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
    )
    await answer_all(
        client,
        fake_chat,
        specialist_tokens,
        match["id"],
        answers=["Concrete answer about a real migration."],
        assessment=assessment_of(0.75),
    )

    interview = (await _report(client, company_tokens, match["id"]))["report"]["interview"]
    assert interview["completed"] is True
    assert interview["overall_score"] == 0.75
    first = interview["questions"][0]
    assert first["asked_because"]  # the rationale for asking, not just the question
    assert first["answered"] is True
    assert first["answer_input_mode"] == "text"
    assert "content only" in interview["scored_on"].lower()


async def test_report_lists_only_the_systems_that_were_actually_used(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-sys@example.com"
    )
    body = await _report(client, company_tokens, match["id"])
    keys = {system["key"] for system in body["report"]["ai_systems"]}

    assert {"ranking", "embedding", "intake"} <= keys
    # no interview was conducted and no contract drafted
    assert "interview_assessment" not in keys
    assert "contract" not in keys
    assert body["report"]["interview"] is None
    for system in body["report"]["ai_systems"]:
        assert len(system["definition_fingerprint"]) == 16


async def test_signature_verifies_and_tampering_is_detected(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-sig@example.com"
    )
    body = await _report(client, company_tokens, match["id"])
    report = body["report"]
    assert report["signature"]["algorithm"] == "HMAC-SHA256"

    genuine = await client.post("/api/v1/transparency-reports/verify", json={"report": report})
    assert genuine.status_code == 200, genuine.text
    assert genuine.json()["valid"] is True
    assert genuine.json()["report_id"] == report["report_id"]

    forged = copy.deepcopy(report)
    forged["ranking"]["total_score"] = 0.99
    tampered = await client.post("/api/v1/transparency-reports/verify", json={"report": forged})
    assert tampered.json()["valid"] is False
    assert "does not carry a valid MatchIT signature" in tampered.json()["detail"]


async def test_verification_needs_no_account(client, fake_chat):
    """An auditor holding the document must be able to check it without one."""
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-anon@example.com"
    )
    report = (await _report(client, company_tokens, match["id"]))["report"]

    response = await client.post(
        "/api/v1/transparency-reports/verify", json={"report": report}
    )  # deliberately no Authorization header
    assert response.status_code == 200
    assert response.json()["valid"] is True


async def test_verification_rejects_junk_without_raising(client):
    for payload in ({}, {"signature": "not-a-dict"}, {"signature": {"value": 7}}):
        response = await client.post(
            "/api/v1/transparency-reports/verify", json={"report": payload}
        )
        assert response.status_code == 200, response.text
        assert response.json()["valid"] is False


async def test_report_names_nobody(client, fake_chat):
    """The document gets forwarded; it identifies the candidacy, not the person."""
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-priv@example.com"
    )
    body = await _report(client, company_tokens, match["id"])
    engagement = body["report"]["engagement"]

    assert engagement["specialist_reference"].startswith("SP-")
    assert engagement["specialist_reference"] == specialist_reference(
        __import__("uuid").UUID(match["specialist_id"])
    )
    serialised = str(body)
    assert "@example.com" not in serialised
    assert "Test User" not in serialised


async def test_markdown_renders_what_the_json_says(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-md@example.com"
    )
    body = await _report(client, company_tokens, match["id"])
    markdown = body["markdown"]

    assert markdown.startswith("# AI transparency report")
    assert body["report"]["report_id"] in markdown
    assert body["report"]["signature"]["value"] in markdown
    assert "No screening interview was conducted." in markdown
    for component in body["report"]["ranking"]["components"]:
        assert f"| {component['component']} |" in markdown


async def test_issuing_a_report_is_audited(client, fake_chat):
    """Who asked for a decision record, and when, is itself worth recording."""
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-audit@example.com"
    )
    body = await _report(client, company_tokens, match["id"])

    admin = await make_admin(client, email="tr-admin@example.com")
    entries = (
        await client.get(
            "/api/v1/admin/audit?action=transparency_report_issued",
            headers=auth_headers(admin),
        )
    ).json()
    assert len(entries) == 1
    assert entries[0]["target_id"] == match["id"]
    assert entries[0]["context"] == {
        "party": "company",
        "report_id": body["report"]["report_id"],
    }


async def test_a_stranger_cannot_read_the_report(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="tr-str@example.com"
    )
    stranger, _ = await create_specialist(client, email="tr-stranger@example.com")
    response = await client.get(
        f"/api/v1/matches/{match['id']}/transparency-report", headers=auth_headers(stranger)
    )
    assert response.status_code == 404  # existence is not confirmed to non-parties


def test_signature_is_not_the_raw_application_secret():
    """Key separation: a report signature must not be forgeable from another use."""
    import hashlib
    import hmac

    from app.services.transparency import canonical_json

    secret = "test-secret-0123456789abcdef0123456789abcdef"
    service = TransparencyService(secret)
    body = {"report_id": "abc", "engagement": {"match_id": "1"}}

    naive = hmac.new(
        secret.encode(), canonical_json(body).encode(), hashlib.sha256
    ).hexdigest()
    assert service.sign(body) != naive


def test_canonical_json_survives_a_round_trip():
    """Verification must not depend on key order or whitespace in transit."""
    import json

    from app.services.transparency import canonical_json

    service = TransparencyService("secret-value")
    body = {"b": 1, "a": {"z": [1, 2], "y": "ü"}}
    signature = service.sign(body)

    reordered = json.loads(json.dumps({"a": {"y": "ü", "z": [1, 2]}, "b": 1}, indent=4))
    assert service.sign(reordered) == signature
    assert canonical_json(reordered) == canonical_json(body)
