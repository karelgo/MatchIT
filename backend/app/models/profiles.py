import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JsonVariant, TimestampedBase
from app.models.user import User


class RemotePreference(enum.StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class SpecialistProfile(TimestampedBase):
    __tablename__ = "specialist_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    headline: Mapped[str] = mapped_column(String(200))
    bio: Mapped[str] = mapped_column(Text, default="")
    # [{"name": "python", "level": 9, "years": 8}]
    skills: Mapped[list[dict]] = mapped_column(JsonVariant, default=list)
    languages: Mapped[list[str]] = mapped_column(JsonVariant, default=list)  # ISO 639-1
    certifications: Mapped[list[str]] = mapped_column(JsonVariant, default=list)
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    hourly_rate: Mapped[float | None] = mapped_column(Float, default=None)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    hours_per_week: Mapped[int] = mapped_column(Integer, default=40)
    available_from: Mapped[date | None] = mapped_column(Date, default=None)
    remote_preference: Mapped[RemotePreference] = mapped_column(
        Enum(RemotePreference, native_enum=False, length=10), default=RemotePreference.REMOTE
    )
    country: Mapped[str] = mapped_column(String(2), default="NL")  # ISO 3166-1 alpha-2
    city: Mapped[str] = mapped_column(String(100), default="")
    travel_distance_km: Mapped[int] = mapped_column(Integer, default=0)
    github_url: Mapped[str | None] = mapped_column(String(500), default=None)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), default=None)
    website_url: Mapped[str | None] = mapped_column(String(500), default=None)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0)
    trust_breakdown: Mapped[dict] = mapped_column(JsonVariant, default=dict)

    user: Mapped[User] = relationship()


class CompanyProfile(TimestampedBase):
    __tablename__ = "company_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(100), default="")
    size: Mapped[str] = mapped_column(String(50), default="")
    country: Mapped[str] = mapped_column(String(2), default="NL")
    city: Mapped[str] = mapped_column(String(100), default="")
    website: Mapped[str | None] = mapped_column(String(500), default=None)
    description: Mapped[str] = mapped_column(Text, default="")
    is_verified: Mapped[bool] = mapped_column(default=False)

    user: Mapped[User] = relationship()
