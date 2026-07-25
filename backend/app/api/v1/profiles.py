from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import (
    CurrentCompanyProfile,
    CurrentSpecialistProfile,
    CurrentUser,
    DbSession,
    get_matching_engine,
)
from app.models import COMPANY_ROLES, SPECIALIST_ROLES, CompanyProfile, SpecialistProfile
from app.schemas.api import (
    CompanyProfileRequest,
    CompanyProfileResponse,
    SpecialistProfileRequest,
    SpecialistProfileResponse,
    UserResponse,
)
from app.services.matching import MatchingEngine

router = APIRouter(tags=["profiles"])

MatchingEngineDep = Annotated[MatchingEngine, Depends(get_matching_engine)]


@router.get("/users/me", response_model=UserResponse)
async def me(user: CurrentUser):
    return user


def _apply_specialist(profile: SpecialistProfile, body: SpecialistProfileRequest) -> None:
    data = body.model_dump()
    data["skills"] = [s.model_dump() for s in body.skills]
    for key, value in data.items():
        setattr(profile, key, value)


@router.put("/specialists/me", response_model=SpecialistProfileResponse)
async def upsert_specialist_profile(
    body: SpecialistProfileRequest,
    user: CurrentUser,
    db: DbSession,
    engine: MatchingEngineDep,
):
    if user.role not in SPECIALIST_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "specialist role required")
    profile = await db.scalar(
        select(SpecialistProfile).where(SpecialistProfile.user_id == user.id)
    )
    if profile is None:
        profile = SpecialistProfile(user_id=user.id, headline=body.headline)
        db.add(profile)
    _apply_specialist(profile, body)
    await db.flush()
    await engine.index_specialist(profile)
    await db.commit()
    return profile


@router.get("/specialists/me", response_model=SpecialistProfileResponse)
async def get_my_specialist_profile(profile: CurrentSpecialistProfile):
    return profile


@router.put("/companies/me", response_model=CompanyProfileResponse)
async def upsert_company_profile(body: CompanyProfileRequest, user: CurrentUser, db: DbSession):
    if user.role not in COMPANY_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "company role required")
    profile = await db.scalar(select(CompanyProfile).where(CompanyProfile.user_id == user.id))
    if profile is None:
        profile = CompanyProfile(user_id=user.id, name=body.name)
        db.add(profile)
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    await db.commit()
    return profile


@router.get("/companies/me", response_model=CompanyProfileResponse)
async def get_my_company_profile(profile: CurrentCompanyProfile):
    return profile
