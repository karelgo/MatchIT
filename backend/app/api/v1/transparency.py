"""Explainability endpoints: transparency reports, AI system cards, match feedback.

These are the artifacts that make an automated hiring decision arguable by the
person it was about. They read persisted data and call no model, so they cost
nothing and are always available.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.ai.schemas import AssignmentRequirements
from app.api.deps import AuditDep, CurrentUser, DbSession, load_match, rate_limit, viewer_role
from app.models import AuditAction, Decision, Interview
from app.schemas.api import (
    AISystemCard,
    AISystemsResponse,
    FeedbackFactorView,
    MatchFeedbackResponse,
    TransparencyReportResponse,
    TransparencyVerifyRequest,
    TransparencyVerifyResponse,
)
from app.services import feedback as feedback_service
from app.services.aisystems import TRANSPARENCY_STATEMENT, cards, model_card_markdown
from app.services.transparency import (
    ReportNotAvailable,
    TransparencyService,
    rank_within_assignment,
    report_markdown,
)

router = APIRouter(tags=["transparency"])


def get_transparency_service(request: Request) -> TransparencyService:
    return request.app.state.transparency_service


@router.get("/matches/{match_id}/transparency-report", response_model=TransparencyReportResponse)
async def transparency_report(
    match_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    audit: AuditDep,
    request: Request,
):
    """The signed record of how this candidacy was handled.

    Both parties get the identical document — see `services/transparency.py` for
    why the interview API's per-viewer projection deliberately does not apply here.
    """
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    service = get_transparency_service(request)
    try:
        report = await service.build(db, match)
    except ReportNotAvailable as unavailable:
        raise HTTPException(status.HTTP_409_CONFLICT, str(unavailable)) from unavailable

    await audit.record(
        db,
        AuditAction.TRANSPARENCY_REPORT_ISSUED,
        actor_user_id=user.id,
        target_type="match",
        target_id=match.id,
        request=request,
        context={"party": viewer, "report_id": report["report_id"]},
    )
    await db.commit()
    return TransparencyReportResponse(report=report, markdown=report_markdown(report))


@router.post(
    "/transparency-reports/verify",
    response_model=TransparencyVerifyResponse,
    dependencies=[Depends(rate_limit("verify", per_user=False))],
)
async def verify_transparency_report(body: TransparencyVerifyRequest, request: Request):
    """Confirm a report is exactly as MatchIT issued it.

    Unauthenticated on purpose: the point of a signed artifact is that whoever
    holds it — a client, an auditor, a tax inspector, the candidate's lawyer —
    can check it without needing an account here. It reveals nothing, since the
    caller already has the document; it only says whether it has been altered.
    """
    service = get_transparency_service(request)
    valid = service.verify(body.report)
    report_id = body.report.get("report_id")
    return TransparencyVerifyResponse(
        valid=valid,
        report_id=report_id if isinstance(report_id, str) else None,
        detail=(
            "This document was issued by MatchIT and has not been altered."
            if valid
            else "This document does not carry a valid MatchIT signature. It was "
            "either not issued by MatchIT or has been modified since."
        ),
    )


@router.get("/ai/systems", response_model=AISystemsResponse)
async def ai_systems(user: CurrentUser):
    """Every automated system MatchIT runs, documented.

    Authenticated rather than public only because it costs a page render; the
    content is published documentation and the same text ships in `docs/`.
    """
    return AISystemsResponse(
        statement=TRANSPARENCY_STATEMENT,
        systems=[AISystemCard(**card) for card in cards()],
        markdown=model_card_markdown(),
    )


@router.get("/matches/{match_id}/feedback", response_model=MatchFeedbackResponse)
async def match_feedback(match_id: uuid.UUID, user: CurrentUser, db: DbSession):
    """Why this match went the way it did, for the specialist.

    Withheld until the company has decided — before then there is nothing to
    explain, and a running commentary on a live candidacy helps nobody.
    """
    match = await load_match(db, match_id)
    if viewer_role(match, user) != "specialist":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "this feedback is written for the specialist"
        )
    if match.company_decision == Decision.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the company has not decided on this match yet",
        )

    requirements = AssignmentRequirements.model_validate(match.assignment.requirements)
    interview = await db.scalar(select(Interview).where(Interview.match_id == match.id))
    rank, considered = await rank_within_assignment(db, match)
    result = feedback_service.build(
        match,
        requirements,
        match.specialist,
        interview,
        rank=rank,
        candidates_scored=considered,
    )
    return MatchFeedbackResponse(
        match_id=match.id,
        outcome=result.outcome,
        headline=result.headline,
        total_score=result.total_score,
        rank=result.rank,
        candidates_scored=result.candidates_scored,
        cost_you_most=[FeedbackFactorView(**vars(f)) for f in result.cost_you_most],
        worked_in_your_favour=[FeedbackFactorView(**vars(f)) for f in result.worked_in_your_favour],
        interview_score=result.interview_score,
        interview_strengths=result.interview_strengths,
        interview_development_areas=result.interview_development_areas,
        note=result.note,
    )
