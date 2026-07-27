import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase
from app.models.contract import Contract


class InvoiceStatus(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    IN_ESCROW = "in_escrow"
    RELEASED = "released"
    CANCELLED = "cancelled"


class Invoice(TimestampedBase):
    """One billing period on a contract.

    Money is Numeric, never float: 0.1 + 0.2 must be 0.3 on an invoice.
    """

    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("contract_id", "period_start"),)

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE")
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, length=15), default=InvoiceStatus.DRAFT
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    hours: Mapped[float] = mapped_column(Numeric(8, 2))
    hourly_rate: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2))
    vat_rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    vat_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    vat_treatment: Mapped[str] = mapped_column(String(20), default="domestic")
    vat_note: Mapped[str] = mapped_column(String(300), default="")
    total: Mapped[float] = mapped_column(Numeric(12, 2))

    commission_rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    commission_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    specialist_payout: Mapped[float] = mapped_column(Numeric(12, 2))

    payment_reference: Mapped[str | None] = mapped_column(String(255), default=None)

    contract: Mapped[Contract] = relationship()
