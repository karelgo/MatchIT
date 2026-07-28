import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import AssignmentRequirements, InterviewPlan
from app.api.deps import CurrentUser, DbSession, load_match, viewer_role
from app.models import (
    Interview,
    InterviewStatus,
    Match,
    MatchStatus,
    SpecialistProfile,
)
from app.schemas.api import (
    AssessmentView,
    InterviewAnswerRequest,
    InterviewQuestionView,
    InterviewResponse,
    TranscriptEntry,
)
from app.services.interview import InterviewService
from app.services.transcription import (
    MAX_AUDIO_BYTES,
    Transcriber,
    TranscriptionError,
    check_audio,
)
from app.services.trust import TrustScoreService, TrustSignals

router = APIRouter(tags=["interviews"])


def get_interview_service(request: Request) -> InterviewService:
    return request.app.state.interview_service


InterviewDep = Annotated[InterviewService, Depends(get_interview_service)]


def _to_response(interview: Interview, viewer: str) -> InterviewResponse:
    plan = InterviewPlan.model_validate(interview.plan)
    questions = [
        InterviewQuestionView(question=q.question, skill=q.skill, rationale=q.rationale)
        for q in plan.questions
    ]
    answered = len(interview.transcript)
    assessment = None
    if interview.assessment is not None:
        raw = interview.assessment
        assessment = AssessmentView(
            overall_score=raw["overall_score"],
            strengths=raw.get("strengths", []),
            development_areas=raw.get("development_areas", []),
            # Risks, the hire recommendation and the per-question breakdown are
            # written for the hiring manager, not the candidate.
            concerns=raw.get("concerns", []) if viewer == "company" else None,
            recommendation=raw.get("recommendation") if viewer == "company" else None,
            summary=raw.get("summary") if viewer == "company" else None,
            per_question=raw.get("per_question", []) if viewer == "company" else None,
        )
    return InterviewResponse(
        id=interview.id,
        match_id=interview.match_id,
        status=interview.status.value,
        gap_summary=plan.gap_summary,
        questions=questions,
        transcript=[TranscriptEntry(**entry) for entry in interview.transcript],
        current_question=questions[answered] if answered < len(questions) else None,
        answered_count=answered,
        total_questions=len(questions),
        assessment=assessment,
        created_at=interview.created_at,
    )


async def _get_interview(db: AsyncSession, match_id: uuid.UUID) -> Interview | None:
    return await db.scalar(select(Interview).where(Interview.match_id == match_id))


@router.post("/matches/{match_id}/interview", response_model=InterviewResponse)
async def start_interview(
    match_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    interviews: InterviewDep,
):
    """Generate the interview for a match. Idempotent — returns the existing one."""
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    if match.status == MatchStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "match is closed")

    existing = await _get_interview(db, match_id)
    if existing is not None:
        return _to_response(existing, viewer)

    requirements = AssignmentRequirements.model_validate(match.assignment.requirements)
    plan = await interviews.plan(requirements, match.specialist)
    interview = Interview(match_id=match_id, plan=plan.model_dump(mode="json"), transcript=[])
    db.add(interview)
    await db.commit()
    return _to_response(interview, viewer)


@router.get("/matches/{match_id}/interview", response_model=InterviewResponse)
async def get_interview(match_id: uuid.UUID, user: CurrentUser, db: DbSession):
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    interview = await _get_interview(db, match_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no interview for this match")
    return _to_response(interview, viewer)


@router.post("/matches/{match_id}/interview/answer", response_model=InterviewResponse)
async def answer_interview(
    match_id: uuid.UUID,
    body: InterviewAnswerRequest,
    user: CurrentUser,
    db: DbSession,
    interviews: InterviewDep,
    request: Request,
):
    """Submit the answer to the current question; the last answer triggers scoring."""
    match, interview = await _open_interview(db, match_id, user)
    return await _record_answer(
        match, interview, body.answer, body.input_mode, db, interviews, request
    )


@router.post("/matches/{match_id}/interview/answer/audio", response_model=InterviewResponse)
async def answer_interview_with_audio(
    match_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    interviews: InterviewDep,
    request: Request,
    file: UploadFile,
    language: str | None = None,
):
    """Answer by voice. The audio is transcribed and then discarded.

    Only the transcript is stored, scored and reported — nothing is inferred from
    the recording itself, which is why the recording does not outlive the request.
    Clients that can transcribe on-device should do that instead and post text with
    `input_mode: "voice"`; this endpoint exists for the ones that cannot.
    """
    match, interview = await _open_interview(db, match_id, user)

    data = await file.read(MAX_AUDIO_BYTES + 1)
    transcriber: Transcriber = request.app.state.transcriber
    try:
        check_audio(data, file.filename or "")
        answer = await transcriber.transcribe(
            data, filename=file.filename or "answer.m4a", language=language
        )
    except TranscriptionError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    del data

    return await _record_answer(match, interview, answer, "voice", db, interviews, request)


async def _open_interview(
    db: AsyncSession, match_id: uuid.UUID, user
) -> tuple[Match, Interview]:
    """Load the match and its in-progress interview, or explain why not."""
    match = await load_match(db, match_id)
    if viewer_role(match, user) != "specialist":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the specialist answers")

    interview = await _get_interview(db, match_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no interview for this match")
    if interview.status == InterviewStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "interview already completed")
    if len(interview.transcript) >= len(InterviewPlan.model_validate(interview.plan).questions):
        raise HTTPException(status.HTTP_409_CONFLICT, "no question pending")
    return match, interview


async def _record_answer(
    match: Match,
    interview: Interview,
    answer: str,
    input_mode: str,
    db: AsyncSession,
    interviews: InterviewService,
    request: Request,
) -> InterviewResponse:
    plan = InterviewPlan.model_validate(interview.plan)
    answered = len(interview.transcript)

    # JSON columns need a new list object for SQLAlchemy to detect the change
    interview.transcript = [
        *interview.transcript,
        {
            "question": plan.questions[answered].question,
            "answer": answer,
            "input_mode": input_mode,
        },
    ]

    if len(interview.transcript) == len(plan.questions):
        requirements = AssignmentRequirements.model_validate(match.assignment.requirements)
        assessment = await interviews.assess(requirements, match.specialist, interview.transcript)
        interview.assessment = assessment.model_dump(mode="json")
        interview.score = assessment.overall_score
        interview.status = InterviewStatus.COMPLETED
        _apply_trust_score(request, match.specialist, assessment.overall_score)

    await db.commit()
    return _to_response(interview, "specialist")


def _apply_trust_score(
    request: Request, profile: SpecialistProfile, interview_score: float
) -> None:
    """Fold the interview result into the specialist's trust score.

    Only the factors the platform can currently evidence are supplied; the rest
    (reviews, completed projects, payment history) stay zero until the epics that
    produce them ship, so the score never overstates what we know.
    """
    trust: TrustScoreService = request.app.state.trust_service
    score, breakdown = trust.compute(
        TrustSignals(
            identity_verified=profile.user.is_verified,
            interview_score=interview_score,
            certifications_total=len(profile.certifications),
        )
    )
    profile.trust_score = score
    profile.trust_breakdown = breakdown
