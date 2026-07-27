"""EU VAT for cross-border B2B services.

Only the rules this platform actually hits: a specialist invoicing a company for
services. The place of supply for B2B services is where the customer is
established, which is what makes reverse charge the common case here.

This is a deliberate simplification of a genuinely complicated area — it is
correct for the standard case and refuses to guess outside it. It is not tax
advice, and the rate table needs an owner who watches it.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Standard rates, in percent. Reduced rates do not apply to IT services.
EU_STANDARD_VAT_RATES: dict[str, Decimal] = {
    "AT": Decimal("20"), "BE": Decimal("21"), "BG": Decimal("20"), "CY": Decimal("19"),
    "CZ": Decimal("21"), "DE": Decimal("19"), "DK": Decimal("25"), "EE": Decimal("22"),
    "ES": Decimal("21"), "FI": Decimal("25.5"), "FR": Decimal("20"), "GR": Decimal("24"),
    "HR": Decimal("25"), "HU": Decimal("27"), "IE": Decimal("23"), "IT": Decimal("22"),
    "LT": Decimal("21"), "LU": Decimal("17"), "LV": Decimal("21"), "MT": Decimal("18"),
    "NL": Decimal("21"), "PL": Decimal("23"), "PT": Decimal("23"), "RO": Decimal("21"),
    "SE": Decimal("25"), "SI": Decimal("22"), "SK": Decimal("23"),
}


class VatTreatment:
    DOMESTIC = "domestic"
    REVERSE_CHARGE = "reverse_charge"
    OUTSIDE_SCOPE = "outside_scope"


@dataclass
class VatAssessment:
    rate_percent: Decimal
    treatment: str
    note: str

    @property
    def is_zero_rated(self) -> bool:
        return self.rate_percent == 0


def money(amount: Decimal) -> Decimal:
    """Round to cents, half-up — the convention invoices are expected to use."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def assess_vat(supplier_country: str, customer_country: str) -> VatAssessment:
    supplier = supplier_country.upper()
    customer = customer_country.upper()

    if supplier == customer:
        rate = EU_STANDARD_VAT_RATES.get(supplier)
        if rate is None:
            return VatAssessment(
                Decimal("0"),
                VatTreatment.OUTSIDE_SCOPE,
                f"No EU VAT rate on file for {supplier}; charged without VAT pending review.",
            )
        return VatAssessment(rate, VatTreatment.DOMESTIC, f"Domestic supply in {supplier}.")

    if supplier in EU_STANDARD_VAT_RATES and customer in EU_STANDARD_VAT_RATES:
        return VatAssessment(
            Decimal("0"),
            VatTreatment.REVERSE_CHARGE,
            "Intra-EU B2B services: VAT reverse-charged to the customer "
            "(Art. 196 VAT Directive).",
        )

    return VatAssessment(
        Decimal("0"),
        VatTreatment.OUTSIDE_SCOPE,
        "Supply outside the EU VAT area; no EU VAT charged.",
    )
