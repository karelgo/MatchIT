import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.schemas import AssignmentRequirements
from app.api.deps import (
    CurrentCompanyProfile,
    CurrentSpecialistProfile,
    CurrentUser,
    DbSession,
    get_intake_service,
    get_matching_engine,
)
from app.models import (
    Assignment,
    AssignmentStatus,
    CompanyProfile,
    Decision,
    Match,
    MatchStatus,
    SpecialistProfile,
)
from app.schemas.api import (
    AssignmentCreateRequest,
    AssignmentResponse,
    MatchDecisionRequest,
    MatchResponse,
)
from app.services.intake import IntakeService
from app.services.matching import MatchingEngine

router = APIRouter(tags=["assignments"])

IntakeDep = Annotated[IntakeService, Depends(get_intake_service)]
MatchingDep = Annotated[MatchingEngine, Depends(get_matching_engine)]

MAX_MATCHES_PER_ASSIGNMENT = 20


@router.post(
    "/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def create_assignment(
    body: AssignmentCreateRequest,
    company: CurrentCompanyProfile,
    db: DbSession,
    intake: IntakeDep,
):
    requirements = await intake.extract(body.description)
    assignment = Assignment(
        company_id=company.id,
        raw_description=body.description,
        requirements=requirements.model_dump(mode="json"),
        status=AssignmentStatus.OPEN,
    )
    db.add(assignment)
    await db.commit()
    return assignment


@router.get("/assignments", response_model=list[AssignmentResponse])
async def list_assignments(company: CurrentCompanyProfile, db: DbSession):
    result = await db.scalars(
        select(Assignment)
        .where(Assignment.company_id == company.id)
        .order_by(Assignment.created_at.desc())
    )
    return list(result)


async def _get_company_assignment(
    db: DbSession, company_id: uuid.UUID, assignment_id: uuid.UUID
) -> Assignment:
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None or assignment.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assignment not found")
    return assignment


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: uuid.UUID, company: CurrentCompanyProfile, db: DbSession
):
    return await _get_company_assignment(db, company.id, assignment_id)


@router.post("/assignments/{assignment_id}/matches", response_model=list[MatchResponse])
async def generate_matches(
    assignment_id: uuid.UUID,
    company: CurrentCompanyProfile,
    db: DbSession,
    engine: MatchingDep,
):
    assignment = await _get_company_assignment(db, company.id, assignment_id)
    requirements = AssignmentRequirements.model_validate(assignment.requirements)

    candidates = list(await db.scalars(select(SpecialistProfile)))
    ranked = await engine.rank(requirements, candidates)

    existing = {
        m.specialist_id: m
        for m in await db.scalars(select(Match).where(Match.assignment_id == assignment.id))
    }
    for candidate in ranked[:MAX_MATCHES_PER_ASSIGNMENT]:
        match = existing.get(candidate.profile.id)
        if match is None:
            db.add(
                Match(
                    assignment_id=assignment.id,
                    specialist_id=candidate.profile.id,
                    score=candidate.score,
                    breakdown=candidate.breakdown,
                )
            )
        elif match.status == MatchStatus.SUGGESTED:
            match.score = candidate.score
            match.breakdown = candidate.breakdown
    await db.commit()
    return await _list_matches(db, assignment.id)


async def _list_matches(db: DbSession, assignment_id: uuid.UUID) -> list[Match]:
    result = await db.scalars(
        select(Match)
        .where(Match.assignment_id == assignment_id)
        .options(selectinload(Match.specialist), selectinload(Match.assignment))
        .order_by(Match.score.desc())
    )
    return list(result)


@router.get("/assignments/{assignment_id}/matches", response_model=list[MatchResponse])
async def list_matches(
    assignment_id: uuid.UUID, company: CurrentCompanyProfile, db: DbSession
):
    await _get_company_assignment(db, company.id, assignment_id)
    return await _list_matches(db, assignment_id)


@router.get("/matches/inbox", response_model=list[MatchResponse])
async def specialist_inbox(profile: CurrentSpecialistProfile, db: DbSession):
    """Opportunity deck for the signed-in specialist: open, undecided matches."""
    result = await db.scalars(
        select(Match)
        .where(
            Match.specialist_id == profile.id,
            Match.specialist_decision == Decision.PENDING,
            Match.status == MatchStatus.SUGGESTED,
        )
        .options(selectinload(Match.specialist), selectinload(Match.assignment))
        .order_by(Match.score.desc())
    )
    return list(result)


@router.post("/matches/{match_id}/decision", response_model=MatchResponse)
async def decide_match(
    match_id: uuid.UUID,
    body: MatchDecisionRequest,
    user: CurrentUser,
    db: DbSession,
):
    if body.decision == Decision.PENDING:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "decision must be final")
    match = await db.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(selectinload(Match.specialist), selectinload(Match.assignment))
    )
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")

    specialist = match.specialist
    assignment = await db.get(Assignment, match.assignment_id)
    company = assignment.company_id if assignment else None
    if specialist.user_id == user.id:
        match.specialist_decision = body.decision
    else:
        company_profile = await db.scalar(
            select(CompanyProfile).where(CompanyProfile.user_id == user.id)
        )
        if company_profile is None or company_profile.id != company:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not a party to this match")
        match.company_decision = body.decision

    if Decision.REJECTED in (match.company_decision, match.specialist_decision):
        match.status = MatchStatus.CLOSED
    elif match.company_decision == Decision.ACCEPTED == match.specialist_decision:
        match.status = MatchStatus.MUTUAL
    await db.commit()
    return match
