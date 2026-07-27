import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JsonVariant, TimestampedBase
from app.models.assignment import Match


class InterviewStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Interview(TimestampedBase):
    """An AI screening interview for one match."""

    __tablename__ = "interviews"

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, native_enum=False, length=15), default=InterviewStatus.IN_PROGRESS
    )
    # validated InterviewPlan
    plan: Mapped[dict] = mapped_column(JsonVariant, default=dict)
    # [{"question": str, "answer": str}] in ask order
    transcript: Mapped[list[dict]] = mapped_column(JsonVariant, default=list)
    # validated InterviewAssessment, populated on completion
    assessment: Mapped[dict | None] = mapped_column(JsonVariant, default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)

    match: Mapped[Match] = relationship()
