import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JsonVariant, TimestampedBase
from app.models.profiles import CompanyProfile, SpecialistProfile


class AssignmentStatus(enum.StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    MATCHED = "matched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Decision(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MatchStatus(enum.StrEnum):
    SUGGESTED = "suggested"
    MUTUAL = "mutual"
    CLOSED = "closed"


class Assignment(TimestampedBase):
    __tablename__ = "assignments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="CASCADE")
    )
    raw_description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[dict] = mapped_column(JsonVariant, default=dict)
    # [{"role": "company"|"concierge", "content": str}] — the intake dialogue
    intake_history: Mapped[list[dict]] = mapped_column(JsonVariant, default=list)
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, native_enum=False, length=15), default=AssignmentStatus.DRAFT
    )

    company: Mapped[CompanyProfile] = relationship()
    matches: Mapped[list["Match"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class Match(TimestampedBase):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("assignment_id", "specialist_id"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE")
    )
    specialist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("specialist_profiles.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict] = mapped_column(JsonVariant, default=dict)
    company_decision: Mapped[Decision] = mapped_column(
        Enum(Decision, native_enum=False, length=10), default=Decision.PENDING
    )
    specialist_decision: Mapped[Decision] = mapped_column(
        Enum(Decision, native_enum=False, length=10), default=Decision.PENDING
    )
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, native_enum=False, length=10), default=MatchStatus.SUGGESTED
    )

    assignment: Mapped[Assignment] = relationship(back_populates="matches")
    specialist: Mapped[SpecialistProfile] = relationship()
