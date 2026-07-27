from decimal import Decimal

import pytest

from app.services.payments import (
    FakePaymentProvider,
    PaymentError,
    compute_invoice,
)
from app.services.vat import VatTreatment, assess_vat, money
from tests.conftest import auth_headers, create_company, create_specialist, make_requirements
from tests.test_chat import DESCRIPTION
from tests.test_contracts import TERMS, draft_of

PERIOD = {"period_start": "2026-09-01", "period_end": "2026-09-30", "hours": 120}


# ---- VAT ----


def test_domestic_supply_carries_the_local_rate():
    assessment = assess_vat("NL", "NL")
    assert assessment.rate_percent == Decimal("21")
    assert assessment.treatment == VatTreatment.DOMESTIC


def test_intra_eu_b2b_is_reverse_charged():
    assessment = assess_vat("NL", "DE")
    assert assessment.rate_percent == Decimal("0")
    assert assessment.treatment == VatTreatment.REVERSE_CHARGE
    assert "reverse-charged" in assessment.note


def test_supply_outside_the_eu_carries_no_eu_vat():
    assert assess_vat("NL", "US").treatment == VatTreatment.OUTSIDE_SCOPE
    assert assess_vat("US", "US").treatment == VatTreatment.OUTSIDE_SCOPE


def test_money_rounds_half_up_to_cents():
    assert money(Decimal("10.005")) == Decimal("10.01")
    assert money(Decimal("10.004")) == Decimal("10.00")


# ---- invoice arithmetic ----


def test_commission_is_taken_on_the_net_fee_not_on_vat():
    """VAT is money collected for a tax authority; a platform fee on it would be
    a fee on somebody else's tax."""
    amounts = compute_invoice(
        hours=Decimal("100"),
        hourly_rate=Decimal("100"),
        vat=assess_vat("NL", "NL"),  # 21%
        commission_rate_percent=Decimal("10"),
    )
    assert amounts.subtotal == Decimal("10000.00")
    assert amounts.vat_amount == Decimal("2100.00")
    assert amounts.total == Decimal("12100.00")
    assert amounts.commission_amount == Decimal("1000.00")  # 10% of 10000, not of 12100
    assert amounts.specialist_payout == Decimal("9000.00")


def test_reverse_charge_invoice_has_no_vat_line():
    amounts = compute_invoice(
        hours=Decimal("10"),
        hourly_rate=Decimal("120"),
        vat=assess_vat("NL", "DE"),
        commission_rate_percent=Decimal("12"),
    )
    assert amounts.vat_amount == Decimal("0.00")
    assert amounts.total == amounts.subtotal == Decimal("1200.00")
    assert amounts.specialist_payout == Decimal("1056.00")


def test_amounts_are_exact_to_the_cent():
    """Float arithmetic would drift here; Decimal must not."""
    amounts = compute_invoice(
        hours=Decimal("7.35"),
        hourly_rate=Decimal("133.33"),
        vat=assess_vat("NL", "NL"),
        commission_rate_percent=Decimal("12.5"),
    )
    # 7.35 * 133.33 = 979.9755, which must round to 979.98 and not drift
    assert amounts.subtotal == Decimal("979.98")
    # the two decompositions must reconcile exactly, with no lost cent
    assert amounts.commission_amount + amounts.specialist_payout == amounts.subtotal
    assert amounts.subtotal + amounts.vat_amount == amounts.total


# ---- provider ----


async def test_escrow_cannot_be_released_twice():
    provider = FakePaymentProvider()
    await provider.hold_in_escrow(amount=Decimal("100"), currency="EUR", reference="inv-1")
    await provider.release(reference="inv-1", payout=Decimal("88"))
    with pytest.raises(PaymentError):
        await provider.release(reference="inv-1", payout=Decimal("88"))


async def test_releasing_an_unknown_reference_fails():
    with pytest.raises(PaymentError):
        await FakePaymentProvider().release(reference="nope", payout=Decimal("1"))


# ---- API ----


async def active_contract(client, fake_chat, *, company_email: str, specialist_country="NL"):
    specialist_tokens, specialist_profile = await create_specialist(
        client, email=f"pay-spec-{company_email}"
    )
    if specialist_country != "NL":
        await client.put(
            "/api/v1/specialists/me",
            headers=auth_headers(specialist_tokens),
            json={
                "headline": "Fabric architect",
                "skills": [{"name": "microsoft fabric", "level": 9, "years": 3}],
                "hourly_rate": 120,
                "country": specialist_country,
            },
        )
    company_tokens = await create_company(client, email=company_email)
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
    await client.post(
        f"/api/v1/matches/{match['id']}/decision",
        headers=auth_headers(company_tokens),
        json={"decision": "accepted"},
    )
    fake_chat.responses.append(draft_of())
    contract = (
        await client.post(
            f"/api/v1/matches/{match['id']}/contract",
            headers=auth_headers(company_tokens),
            json=TERMS,
        )
    ).json()
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(specialist_tokens)
    )
    assert specialist_profile
    return specialist_tokens, company_tokens, contract


async def test_invoice_escrow_and_release(client, fake_chat, payment_provider):
    specialist_tokens, company_tokens, contract = await active_contract(
        client, fake_chat, company_email="pay1@example.com"
    )

    issued = await client.post(
        f"/api/v1/contracts/{contract['id']}/invoices",
        headers=auth_headers(specialist_tokens),
        json=PERIOD,
    )
    assert issued.status_code == 200, issued.text
    invoice = issued.json()
    assert invoice["status"] == "issued"
    # both parties are NL, so this is a domestic supply at 21%
    assert invoice["vat_treatment"] == "domestic"
    assert invoice["vat_rate_percent"] == 21.0
    assert invoice["subtotal"] == 120 * 120.0
    assert invoice["total"] == pytest.approx(invoice["subtotal"] * 1.21)
    assert invoice["commission_amount"] > 0
    assert invoice["specialist_payout"] == pytest.approx(
        invoice["subtotal"] - invoice["commission_amount"]
    )

    paid = await client.post(
        f"/api/v1/invoices/{invoice['id']}/pay", headers=auth_headers(company_tokens)
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "in_escrow"
    # the company is charged the gross total, VAT included
    assert payment_provider.charges[invoice["id"]].amount == Decimal(str(invoice["total"]))

    released = await client.post(
        f"/api/v1/invoices/{invoice['id']}/release", headers=auth_headers(company_tokens)
    )
    assert released.status_code == 200
    assert released.json()["status"] == "released"
    # the specialist receives the net fee, not the gross
    assert payment_provider.released[invoice["id"]] == Decimal(
        str(invoice["specialist_payout"])
    )


async def test_cross_border_invoice_is_reverse_charged(client, fake_chat):
    specialist_tokens, _, contract = await active_contract(
        client, fake_chat, company_email="pay2@example.com", specialist_country="DE"
    )
    invoice = (
        await client.post(
            f"/api/v1/contracts/{contract['id']}/invoices",
            headers=auth_headers(specialist_tokens),
            json=PERIOD,
        )
    ).json()
    assert invoice["vat_treatment"] == "reverse_charge"
    assert invoice["vat_amount"] == 0
    assert invoice["total"] == invoice["subtotal"]
    assert "Art. 196" in invoice["vat_note"]


async def test_a_period_cannot_be_invoiced_twice(client, fake_chat):
    specialist_tokens, _, contract = await active_contract(
        client, fake_chat, company_email="pay3@example.com"
    )
    first = await client.post(
        f"/api/v1/contracts/{contract['id']}/invoices",
        headers=auth_headers(specialist_tokens),
        json=PERIOD,
    )
    assert first.status_code == 200
    duplicate = await client.post(
        f"/api/v1/contracts/{contract['id']}/invoices",
        headers=auth_headers(specialist_tokens),
        json=PERIOD,
    )
    assert duplicate.status_code == 409


async def test_only_the_right_party_can_invoice_pay_and_release(client, fake_chat):
    specialist_tokens, company_tokens, contract = await active_contract(
        client, fake_chat, company_email="pay4@example.com"
    )
    # the company cannot invoice itself
    assert (
        await client.post(
            f"/api/v1/contracts/{contract['id']}/invoices",
            headers=auth_headers(company_tokens),
            json=PERIOD,
        )
    ).status_code == 403

    invoice = (
        await client.post(
            f"/api/v1/contracts/{contract['id']}/invoices",
            headers=auth_headers(specialist_tokens),
            json=PERIOD,
        )
    ).json()

    # the specialist cannot pay their own invoice or release the escrow
    assert (
        await client.post(
            f"/api/v1/invoices/{invoice['id']}/pay", headers=auth_headers(specialist_tokens)
        )
    ).status_code == 403
    await client.post(
        f"/api/v1/invoices/{invoice['id']}/pay", headers=auth_headers(company_tokens)
    )
    assert (
        await client.post(
            f"/api/v1/invoices/{invoice['id']}/release", headers=auth_headers(specialist_tokens)
        )
    ).status_code == 403

    outsider = await create_company(client, email="pay-outsider@example.com")
    assert (
        await client.get(
            f"/api/v1/contracts/{contract['id']}/invoices", headers=auth_headers(outsider)
        )
    ).status_code == 404


async def test_escrow_cannot_be_released_before_payment(client, fake_chat):
    specialist_tokens, company_tokens, contract = await active_contract(
        client, fake_chat, company_email="pay5@example.com"
    )
    invoice = (
        await client.post(
            f"/api/v1/contracts/{contract['id']}/invoices",
            headers=auth_headers(specialist_tokens),
            json=PERIOD,
        )
    ).json()
    assert (
        await client.post(
            f"/api/v1/invoices/{invoice['id']}/release", headers=auth_headers(company_tokens)
        )
    ).status_code == 409


async def test_invoicing_requires_an_active_contract(client, fake_chat):
    """A drafted but unsigned contract cannot be billed against."""
    specialist_tokens, company_tokens = None, None
    specialist_tokens, specialist_profile = await create_specialist(
        client, email="pay6-spec@example.com"
    )
    company_tokens = await create_company(client, email="pay6@example.com")
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
    for tokens in (specialist_tokens, company_tokens):
        await client.post(
            f"/api/v1/matches/{match['id']}/decision",
            headers=auth_headers(tokens),
            json={"decision": "accepted"},
        )
    fake_chat.responses.append(draft_of())
    contract = (
        await client.post(
            f"/api/v1/matches/{match['id']}/contract",
            headers=auth_headers(company_tokens),
            json=TERMS,
        )
    ).json()
    # nobody has signed, so the contract is pending_signatures
    response = await client.post(
        f"/api/v1/contracts/{contract['id']}/invoices",
        headers=auth_headers(specialist_tokens),
        json=PERIOD,
    )
    assert response.status_code == 409
    assert specialist_profile
