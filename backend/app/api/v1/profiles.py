from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.ai.schemas import SkillSource
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
    CVEnrichmentRequest,
    EnrichmentResponse,
    GitHubEnrichmentRequest,
    SpecialistProfileRequest,
    SpecialistProfileResponse,
    UserResponse,
)
from app.services.enrichment import EnrichmentService, NothingToAnalyse, merge_skills
from app.services.github import GitHubUnavailable
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


def _enrichment_result(
    profile: SpecialistProfile,
    before: list[dict],
    source: str,
    summary: str,
) -> dict:
    before_names = {s["name"].strip().lower() for s in before}
    after = profile.skills
    return {
        "source": source,
        "summary": summary,
        "skills_added": sum(1 for s in after if s["name"] not in before_names),
        "skills_updated": sum(
            1
            for s in after
            if s["name"] in before_names and s.get("source", "self_reported") == source
        ),
        "evidence_count": sum(1 for s in after if s.get("evidence")),
        "profile": profile,
    }


@router.post("/specialists/me/enrich/cv", response_model=EnrichmentResponse)
async def enrich_from_cv(
    body: CVEnrichmentRequest,
    profile: CurrentSpecialistProfile,
    db: DbSession,
    engine: MatchingEngineDep,
    request: Request,
):
    """Read a CV into the skill graph, citing evidence for every skill."""
    enrichment: EnrichmentService = request.app.state.enrichment_service
    extraction = await enrichment.from_cv(body.cv_text)

    before = list(profile.skills)
    profile.skills = merge_skills(before, extraction.skills, SkillSource.CV)
    # The CV is the better source for these too, but never blank an existing value
    profile.headline = extraction.headline or profile.headline
    profile.bio = extraction.summary or profile.bio
    profile.years_experience = max(profile.years_experience, extraction.years_experience)
    profile.certifications = sorted({*profile.certifications, *extraction.certifications})
    profile.languages = sorted({*profile.languages, *extraction.languages})

    await db.flush()
    await engine.index_specialist(profile)
    await db.commit()
    return _enrichment_result(profile, before, SkillSource.CV.value, extraction.summary)


@router.post("/specialists/me/enrich/github", response_model=EnrichmentResponse)
async def enrich_from_github(
    body: GitHubEnrichmentRequest,
    profile: CurrentSpecialistProfile,
    db: DbSession,
    engine: MatchingEngineDep,
    request: Request,
):
    """Infer skills from public repositories."""
    enrichment: EnrichmentService = request.app.state.enrichment_service
    try:
        extraction, _ = await enrichment.from_github(body.username)
    except GitHubUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except NothingToAnalyse as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no original public repositories to analyse",
        ) from error

    before = list(profile.skills)
    profile.skills = merge_skills(before, extraction.skills, SkillSource.GITHUB)
    profile.github_url = f"https://github.com/{body.username}"

    await db.flush()
    await engine.index_specialist(profile)
    await db.commit()
    return _enrichment_result(profile, before, SkillSource.GITHUB.value, extraction.summary)


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
