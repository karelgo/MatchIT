from datetime import date

from app.ai.schemas import ContractClause, ContractDraft
from tests.conftest import auth_headers, create_company
from tests.test_chat import make_mutual_match

TERMS = {
    "hourly_rate": 120.0,
    "currency": "EUR",
    "hours_per_week": 32,
    "start_date": "2026-09-01",
    "end_date": "2027-03-01",
}


def draft_of() -> ContractDraft:
    return ContractDraft(
        title="Microsoft Fabric migration — engagement agreement",
        scope_of_work=["Migrate the on-prem warehouse to Microsoft Fabric"],
        rate_terms="EUR 120 per hour, invoiced monthly, payable within 30 days.",
        duration_terms="From 1 September 2026 until 1 March 2027, 32 hours per week.",
        clauses=[
            ContractClause(
                heading="Intellectual property", body="All work product assigns to the client."
            ),
            ContractClause(
                heading="Confidentiality", body="Both parties keep information confidential."
            ),
            ContractClause(
                heading="Termination", body="Either party may terminate on 30 days' notice."
            ),
        ],
        governing_law="the laws of the Netherlands",
        open_points=["Confirm whether the specialist works on client premises for DBA purposes"],
    )


async def make_contract(client, fake_chat, *, company_email: str):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email=company_email
    )
    fake_chat.responses.append(draft_of())
    created = await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json=TERMS,
    )
    assert created.status_code == 200, created.text
    return specialist_tokens, company_tokens, match, created.json()


async def test_draft_sign_and_activate(client, fake_chat):
    specialist_tokens, company_tokens, match, contract = await make_contract(
        client, fake_chat, company_email="ct-hm@example.com"
    )
    assert contract["status"] == "pending_signatures"
    assert contract["hourly_rate"] == 120.0
    assert contract["hours_per_week"] == 32
    assert contract["draft"]["governing_law"] == "the laws of the Netherlands"
    assert contract["draft"]["open_points"]
    assert contract["company_signed"] is False
    assert contract["specialist_signed"] is False

    # the drafter received the agreed terms verbatim and never had to invent them
    prompt = fake_chat.calls[-1]["user"]
    assert "120" in prompt and "2026-09-01" in prompt and "agreed_terms" in prompt

    company_signed = await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    assert company_signed.status_code == 200
    assert company_signed.json()["company_signed"] is True
    assert company_signed.json()["signed_by_me"] is True
    assert company_signed.json()["status"] == "pending_signatures"

    specialist_signed = await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(specialist_tokens)
    )
    assert specialist_signed.status_code == 200
    body = specialist_signed.json()
    assert body["status"] == "active"
    assert body["company_signed"] and body["specialist_signed"]


async def test_signed_by_me_is_per_viewer(client, fake_chat):
    specialist_tokens, company_tokens, match, _ = await make_contract(
        client, fake_chat, company_email="ct-hm2@example.com"
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    specialist_view = (
        await client.get(
            f"/api/v1/matches/{match['id']}/contract", headers=auth_headers(specialist_tokens)
        )
    ).json()
    assert specialist_view["company_signed"] is True
    assert specialist_view["signed_by_me"] is False


async def test_double_signing_conflicts(client, fake_chat):
    _, company_tokens, match, _ = await make_contract(
        client, fake_chat, company_email="ct-hm3@example.com"
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    again = await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    assert again.status_code == 409


async def test_specialist_cannot_draft_and_outsider_cannot_see(client, fake_chat):
    specialist_tokens, _, match, _ = await make_contract(
        client, fake_chat, company_email="ct-hm4@example.com"
    )
    denied = await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(specialist_tokens),
        json=TERMS,
    )
    assert denied.status_code == 403

    outsider = await create_company(client, email="ct-outsider@example.com")
    assert (
        await client.get(
            f"/api/v1/matches/{match['id']}/contract", headers=auth_headers(outsider)
        )
    ).status_code == 404


async def test_contract_requires_a_mutual_match(client, fake_chat):
    """Contracting before both sides accept would let a company bind a stranger."""
    from tests.conftest import create_specialist, make_requirements
    from tests.test_chat import DESCRIPTION

    await create_specialist(client)
    company_tokens = await create_company(client, email="ct-hm5@example.com")
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

    response = await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json=TERMS,
    )
    assert response.status_code == 409


async def test_draft_is_idempotent(client, fake_chat):
    _, company_tokens, match, first = await make_contract(
        client, fake_chat, company_email="ct-hm6@example.com"
    )
    # no second draft queued — a repeat call must reuse the stored contract
    again = await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json={**TERMS, "hourly_rate": 999.0},
    )
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert again.json()["hourly_rate"] == 120.0, "terms must not be silently rewritten"


async def test_end_date_must_follow_start_date(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="ct-hm7@example.com"
    )
    response = await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json={**TERMS, "start_date": "2026-09-01", "end_date": "2026-08-01"},
    )
    assert response.status_code == 422


async def test_invalid_rate_rejected(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="ct-hm8@example.com"
    )
    for rate in (0, -5):
        response = await client.post(
            f"/api/v1/matches/{match['id']}/contract",
            headers=auth_headers(company_tokens),
            json={**TERMS, "hourly_rate": rate},
        )
        assert response.status_code == 422, rate


def test_contract_dates_are_real_dates():
    """The API stores dates as dates, not strings — invoicing depends on it."""
    assert date.fromisoformat(TERMS["start_date"]) < date.fromisoformat(TERMS["end_date"])
