"""Payment provider behind a protocol, and invoice arithmetic.

Escrow model: the company's money is captured when the invoice is paid and held
until the work for that period is accepted, then released to the specialist minus
the platform's commission. The provider is abstracted so Stripe is a deployment
choice, and so the arithmetic can be tested without a network.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from app.services.vat import VatAssessment, money


class PaymentError(Exception):
    pass


@dataclass
class EscrowCharge:
    reference: str
    amount: Decimal
    currency: str


class PaymentProvider(Protocol):
    async def hold_in_escrow(
        self, *, amount: Decimal, currency: str, reference: str
    ) -> EscrowCharge: ...

    async def release(self, *, reference: str, payout: Decimal) -> None: ...


class StripePaymentProvider:
    """Stripe Connect: a manual-capture PaymentIntent is the escrow hold, and
    capture-plus-transfer is the release."""

    def __init__(self, api_key: str):
        if not api_key:
            raise PaymentError("Stripe API key is not configured")
        self._api_key = api_key

    async def hold_in_escrow(
        self, *, amount: Decimal, currency: str, reference: str
    ) -> EscrowCharge:  # pragma: no cover - requires Stripe credentials
        raise PaymentError(
            "StripePaymentProvider is not implemented yet; configure "
            "MATCHIT_PAYMENT_PROVIDER=fake outside production"
        )

    async def release(self, *, reference: str, payout: Decimal) -> None:  # pragma: no cover
        raise PaymentError("StripePaymentProvider is not implemented yet")


@dataclass
class FakePaymentProvider:
    """In-memory provider for tests and local development."""

    charges: dict[str, EscrowCharge] = field(default_factory=dict)
    released: dict[str, Decimal] = field(default_factory=dict)

    async def hold_in_escrow(
        self, *, amount: Decimal, currency: str, reference: str
    ) -> EscrowCharge:
        if amount <= 0:
            raise PaymentError("cannot hold a non-positive amount")
        charge = EscrowCharge(reference=reference, amount=amount, currency=currency)
        self.charges[reference] = charge
        return charge

    async def release(self, *, reference: str, payout: Decimal) -> None:
        if reference not in self.charges:
            raise PaymentError(f"unknown escrow reference: {reference}")
        if reference in self.released:
            raise PaymentError("escrow already released")
        self.released[reference] = payout


@dataclass
class InvoiceAmounts:
    subtotal: Decimal
    vat_amount: Decimal
    total: Decimal
    commission_amount: Decimal
    specialist_payout: Decimal


def compute_invoice(
    *,
    hours: Decimal,
    hourly_rate: Decimal,
    vat: VatAssessment,
    commission_rate_percent: Decimal,
) -> InvoiceAmounts:
    """Invoice arithmetic in Decimal throughout.

    Commission is taken on the net fee, never on VAT: VAT is money collected for
    a tax authority, and charging a platform fee on it would be charging a fee on
    somebody else's tax.
    """
    subtotal = money(hours * hourly_rate)
    vat_amount = money(subtotal * vat.rate_percent / Decimal("100"))
    total = money(subtotal + vat_amount)
    commission_amount = money(subtotal * commission_rate_percent / Decimal("100"))
    specialist_payout = money(subtotal - commission_amount)
    return InvoiceAmounts(
        subtotal=subtotal,
        vat_amount=vat_amount,
        total=total,
        commission_amount=commission_amount,
        specialist_payout=specialist_payout,
    )


def build_payment_provider(settings) -> PaymentProvider:
    if settings.payment_provider == "stripe":
        return StripePaymentProvider(settings.stripe_api_key)
    if settings.payment_provider == "fake":
        return FakePaymentProvider()
    raise ValueError(f"unknown payment_provider: {settings.payment_provider}")
