"""Engagement evidence pack: what it observes, and what it refuses to conclude."""

from app.ai.schemas import ContractClause, ContractDraft
from app.services.evidence import AGAINST, NEUTRAL, SUPPORTS, _clause_topics
from tests.conftest import auth_headers, create_specialist
from tests.test_chat import make_mutual_match
from tests.test_contracts import TERMS, draft_of


def _draft_with(*clauses: tuple[str, str]) -> ContractDraft:
    return ContractDraft(
        title="Engagement agreement",
        scope_of_work=["Design the Fabric target architecture", "Migrate the warehouse"],
        rate_terms="EUR 120 per hour, invoiced monthly, payable in 30 days.",
        duration_terms="Six months from the start date, one month notice.",
        clauses=[ContractClause(heading=heading, body=body) for heading, body in clauses],
        governing_law="the laws of the Netherlands",
        open_points=["Confirm the on-call expectation."],
    )


async def _signed_engagement(client, fake_chat, *, prefix: str, terms: dict | None = None):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email=f"{prefix}-hm@example.com"
    )
    fake_chat.responses.append(draft_of())
    await client.post(
        f"/api/v1/matches/{match['id']}/contract",
        headers=auth_headers(company_tokens),
        json={**TERMS, **(terms or {})},
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(specialist_tokens)
    )
    return specialist_tokens, company_tokens, match


async def _pack(client, tokens, match_id) -> dict:
    response = await client.get(
        f"/api/v1/matches/{match_id}/evidence-pack", headers=auth_headers(tokens)
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_clause_detection_reads_headings_and_bodies_in_both_languages():
    draft = _draft_with(
        ("Intellectual property", "All IP created is assigned to the client."),
        ("Zelfstandigheid", "Partijen beogen uitdrukkelijk geen arbeidsovereenkomst."),
        ("Vervanging", "The specialist may propose a suitably qualified replacement."),
    )
    topics = _clause_topics(draft)

    assert topics["intellectual_property"] == "Intellectual property"
    assert topics["contractor_status"] == "Zelfstandigheid"
    assert topics["substitution"] == "Vervanging"
    assert topics["data_protection"] is None


def test_clause_detection_does_not_invent_a_match():
    """A false positive here would put a claim in an evidence pack that is not true."""
    draft = _draft_with(
        ("Payment", "Invoices are paid within 30 days."),
        ("Deliverables", "The specialist delivers the migrated warehouse."),
        ("Insurance", "The specialist carries professional indemnity cover."),
    )
    topics = _clause_topics(draft)
    assert set(filter(None, topics.values())) == set()


async def test_pack_reports_the_engagement_and_scope(client, fake_chat):
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-basic")
    body = await _pack(client, company_tokens, match["id"])
    pack = body["pack"]

    assert pack["engagement"]["status"] == "active"
    assert pack["engagement"]["hourly_rate"] == TERMS["hourly_rate"]
    assert pack["scope_of_work"]
    assert pack["assignment"]["summary"]
    assert pack["contract_terms"]["governing_law"]


async def test_an_open_ended_contract_is_reported_as_pointing_the_other_way(client, fake_chat):
    """The pack has to be as willing to report bad news as good."""
    _, company_tokens, match = await _signed_engagement(
        client, fake_chat, prefix="ev-open", terms={"end_date": None}
    )
    pack = (await _pack(client, company_tokens, match["id"]))["pack"]

    fixed_term = next(i for i in pack["indicators"] if i["key"] == "fixed_term")
    assert fixed_term["direction"] == AGAINST
    assert fixed_term["observed"] == "open-ended"
    assert pack["indicator_tally"][AGAINST] >= 1


async def test_a_fixed_term_contract_supports_independence(client, fake_chat):
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-fixed")
    pack = (await _pack(client, company_tokens, match["id"]))["pack"]

    fixed_term = next(i for i in pack["indicators"] if i["key"] == "fixed_term")
    assert fixed_term["direction"] == SUPPORTS
    assert TERMS["start_date"] in fixed_term["observed"]


async def test_a_single_client_is_neutral_and_says_why(client, fake_chat):
    """Overstating this would be the most tempting and most dangerous error."""
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-single")
    pack = (await _pack(client, company_tokens, match["id"]))["pack"]

    clients = next(i for i in pack["indicators"] if i["key"] == "multiple_clients")
    assert clients["direction"] == NEUTRAL
    assert "1 distinct company" in clients["observed"]
    assert "Work done elsewhere counts just as much" in clients["why"]


async def test_the_signature_trail_comes_from_the_audit_log(client, fake_chat):
    specialist_tokens, company_tokens, match = await _signed_engagement(
        client, fake_chat, prefix="ev-sig"
    )
    pack = (await _pack(client, specialist_tokens, match["id"]))["pack"]
    signatures = pack["signatures"]

    assert signatures["fully_signed"] is True
    assert signatures["company_signed_at"] is not None
    assert signatures["specialist_signed_at"] is not None
    parties = [entry["context"]["party"] for entry in signatures["audit_trail"]]
    assert parties == ["company", "specialist"]
    assert signatures["audit_trail"][-1]["context"]["activated"] is True
    assert company_tokens  # both parties drove the signing above


async def test_invoices_appear_with_their_vat_treatment(client, fake_chat):
    specialist_tokens, company_tokens, match = await _signed_engagement(
        client, fake_chat, prefix="ev-inv"
    )
    contract = (
        await client.get(
            f"/api/v1/matches/{match['id']}/contract", headers=auth_headers(specialist_tokens)
        )
    ).json()
    created = await client.post(
        f"/api/v1/contracts/{contract['id']}/invoices",
        headers=auth_headers(specialist_tokens),
        json={"period_start": "2026-09-01", "period_end": "2026-09-30", "hours": 120},
    )
    assert created.status_code == 200, created.text

    pack = (await _pack(client, company_tokens, match["id"]))["pack"]
    assert len(pack["invoices"]) == 1
    invoice = pack["invoices"][0]
    assert invoice["hours"] == 120.0
    assert invoice["vat_treatment"]

    own_invoicing = next(i for i in pack["indicators"] if i["key"] == "own_invoicing")
    assert own_invoicing["direction"] == SUPPORTS
    assert "1 invoice(s)" in own_invoicing["observed"]


async def test_the_pack_refuses_to_draw_a_conclusion(client, fake_chat):
    """A checklist that claimed to settle this would be worth less than nothing."""
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-disc")
    body = await _pack(client, company_tokens, match["id"])

    assert "evidence, not a determination" in body["pack"]["disclaimer"]
    assert "do not treat it as the answer" in body["pack"]["disclaimer"]
    assert "a summary, not a score" in body["markdown"]
    # no field anywhere asserts a verdict
    assert "compliant" not in str(body["pack"]).lower()


async def test_dutch_parties_get_the_dba_framing(client, fake_chat):
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-nl")
    pack = (await _pack(client, company_tokens, match["id"]))["pack"]

    assert pack["jurisdiction"]["primary_regime"] == "NL — Wet DBA"
    assert pack["jurisdiction"]["countries"] == ["NL"]
    assert "moratorium ended in 2025" in pack["jurisdiction"]["note"]


async def test_both_parties_can_pull_the_pack_and_a_stranger_cannot(client, fake_chat):
    specialist_tokens, company_tokens, match = await _signed_engagement(
        client, fake_chat, prefix="ev-access"
    )
    for tokens in (specialist_tokens, company_tokens):
        await _pack(client, tokens, match["id"])

    stranger, _ = await create_specialist(client, email="ev-stranger@example.com")
    response = await client.get(
        f"/api/v1/matches/{match['id']}/evidence-pack", headers=auth_headers(stranger)
    )
    assert response.status_code == 404


async def test_no_contract_means_no_pack(client, fake_chat):
    _, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="ev-none-hm@example.com"
    )
    response = await client.get(
        f"/api/v1/matches/{match['id']}/evidence-pack", headers=auth_headers(company_tokens)
    )
    assert response.status_code == 404
    assert "no contract" in response.json()["detail"]


async def test_markdown_carries_the_indicators_and_the_clauses(client, fake_chat):
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-md")
    body = await _pack(client, company_tokens, match["id"])
    markdown = body["markdown"]

    assert markdown.startswith("# Engagement evidence pack")
    for indicator in body["pack"]["indicators"]:
        assert f"| {indicator['label']} |" in markdown
    for clause in body["pack"]["contract_terms"]["clauses"]:
        assert f"### {clause['heading']}" in markdown
    assert "Open points for a lawyer" in markdown


async def test_issuing_a_pack_is_audited(client, fake_chat):
    from tests.test_admin import make_admin

    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-audit")
    await _pack(client, company_tokens, match["id"])

    admin = await make_admin(client, email="ev-admin@example.com")
    entries = (
        await client.get(
            "/api/v1/admin/audit?action=evidence_pack_issued", headers=auth_headers(admin)
        )
    ).json()
    assert len(entries) == 1
    assert entries[0]["context"] == {"party": "company"}


async def test_building_a_pack_costs_no_model_call(client, fake_chat):
    _, company_tokens, match = await _signed_engagement(client, fake_chat, prefix="ev-cost")
    before = len(fake_chat.calls)
    await _pack(client, company_tokens, match["id"])
    assert len(fake_chat.calls) == before
