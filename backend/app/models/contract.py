import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JsonVariant, TimestampedBase
from app.models.assignment import Match


class ContractStatus(enum.StrEnum):
    DRAFT = "draft"
    PENDING_SIGNATURES = "pending_signatures"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Contract(TimestampedBase):
    """An engagement contract for one match.

    Commercial terms live in real columns because they are queried, invoiced and
    reported on; the drafted prose lives in JSON because only humans read it.
    """

    __tablename__ = "contracts"

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, native_enum=False, length=20), default=ContractStatus.DRAFT
    )
    hourly_rate: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    hours_per_week: Mapped[int] = mapped_column(Integer, default=40)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    # validated ContractDraft
    draft: Mapped[dict] = mapped_column(JsonVariant, default=dict)
    company_signed_at: Mapped[datetime | None] = mapped_column(default=None)
    specialist_signed_at: Mapped[datetime | None] = mapped_column(default=None)

    match: Mapped[Match] = relationship()

    @property
    def is_fully_signed(self) -> bool:
        return self.company_signed_at is not None and self.specialist_signed_at is not None
