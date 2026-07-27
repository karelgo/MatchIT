"""GDPR data-subject tooling: portability (export) and erasure."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    CompanyProfile,
    Contract,
    ContractStatus,
    Interview,
    Match,
    Message,
    SpecialistProfile,
    User,
)


class ErasureBlocked(Exception):
    """Erasure refused because a live obligation depends on the account."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value"):  # enums
        return value.value
    return value


def _row(instance, *fields: str) -> dict:
    return {field: _jsonable(getattr(instance, field)) for field in fields}


class PrivacyService:
    """Article 15/20 export and Article 17 erasure."""

    async def export(self, db: AsyncSession, user: User) -> dict:
        """Everything the platform holds about this user, as portable JSON."""
        data: dict[str, Any] = {
            "account": _row(
                user, "id", "email", "full_name", "role", "is_verified", "created_at"
            ),
        }

        specialist = await db.scalar(
            select(SpecialistProfile).where(SpecialistProfile.user_id == user.id)
        )
        if specialist is not None:
            data["specialist_profile"] = _row(
                specialist,
                "id", "headline", "bio", "skills", "languages", "certifications",
                "years_experience", "hourly_rate", "currency", "hours_per_week",
                "available_from", "remote_preference", "country", "city",
                "travel_distance_km", "github_url", "linkedin_url", "website_url",
                "trust_score", "trust_breakdown", "created_at",
            )
            data["matches"] = [
                _row(m, "id", "assignment_id", "score", "breakdown", "status", "created_at")
                for m in await db.scalars(
                    select(Match).where(Match.specialist_id == specialist.id)
                )
            ]
            data["interviews"] = [
                _row(i, "id", "match_id", "status", "transcript", "score", "created_at")
                for i in await db.scalars(
                    select(Interview)
                    .join(Match, Interview.match_id == Match.id)
                    .where(Match.specialist_id == specialist.id)
                )
            ]

        company = await db.scalar(
            select(CompanyProfile).where(CompanyProfile.user_id == user.id)
        )
        if company is not None:
            data["company_profile"] = _row(
                company, "id", "name", "industry", "size", "country", "city",
                "website", "description", "is_verified", "created_at",
            )
            data["assignments"] = [
                _row(a, "id", "raw_description", "requirements", "intake_history",
                     "status", "created_at")
                for a in await db.scalars(
                    select(Assignment).where(Assignment.company_id == company.id)
                )
            ]

        data["messages"] = [
            _row(m, "id", "conversation_id", "content", "created_at")
            for m in await db.scalars(select(Message).where(Message.sender_id == user.id))
        ]
        return data

    async def erase(self, db: AsyncSession, user: User) -> None:
        """Delete the account and everything cascading from it.

        Refused while a contract is active: a signed, in-force engagement is a
        live obligation on both sides, and erasure is not a way out of one.
        Article 17(3)(b)/(e) — complete or cancel it first.
        """
        active = await db.scalar(
            select(Contract)
            .join(Match, Contract.match_id == Match.id)
            .outerjoin(SpecialistProfile, Match.specialist_id == SpecialistProfile.id)
            .outerjoin(Assignment, Match.assignment_id == Assignment.id)
            .outerjoin(CompanyProfile, Assignment.company_id == CompanyProfile.id)
            .where(
                Contract.status == ContractStatus.ACTIVE,
                (SpecialistProfile.user_id == user.id) | (CompanyProfile.user_id == user.id),
            )
            .limit(1)
        )
        if active is not None:
            raise ErasureBlocked(
                "an active contract depends on this account; complete or cancel it first"
            )
        await db.delete(user)
        await db.commit()
