"""Request/response contracts for API v1."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.ai.schemas import AssignmentRequirements
from app.models import AssignmentStatus, Decision, MatchStatus, RemotePreference, UserRole


def _as_utc(value: datetime) -> datetime:
    """Normalise to tz-aware UTC.

    Postgres (`DateTime(timezone=True)`) returns aware datetimes, SQLite returns
    naive ones. Clients must never have to guess a timezone, so every timestamp
    leaving the API goes through here.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UTCDatetime = Annotated[datetime, AfterValidator(_as_utc)]


def _non_blank(value: str) -> str:
    """Reject whitespace-only input and return the trimmed value.

    `min_length` alone lets "   " through, which then strips to an empty string —
    an empty chat message, or an interview question marked answered with nothing.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("must not be blank")
    return trimmed


NonBlankStr = Annotated[str, AfterValidator(_non_blank)]

# ---- auth ----


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AppleSignInRequest(BaseModel):
    identity_token: str
    full_name: str | None = None
    role: UserRole = UserRole.FREELANCER


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_verified: bool
    created_at: UTCDatetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---- profiles ----


class SkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    level: int = Field(ge=0, le=10)
    years: float = Field(default=0, ge=0, le=60)


class SpecialistProfileRequest(BaseModel):
    headline: str = Field(min_length=1, max_length=200)
    bio: str = ""
    skills: list[SkillInput] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    years_experience: int = Field(default=0, ge=0, le=60)
    hourly_rate: float | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    hours_per_week: int = Field(default=40, ge=1, le=80)
    available_from: date | None = None
    remote_preference: RemotePreference = RemotePreference.REMOTE
    country: str = Field(default="NL", min_length=2, max_length=2)
    city: str = ""
    travel_distance_km: int = Field(default=0, ge=0)
    github_url: str | None = None
    linkedin_url: str | None = None
    website_url: str | None = None


class SpecialistProfileResponse(SpecialistProfileRequest):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    trust_score: float
    trust_breakdown: dict[str, float]


class CompanyProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str = ""
    size: str = ""
    country: str = Field(default="NL", min_length=2, max_length=2)
    city: str = ""
    website: str | None = None
    description: str = ""


class CompanyProfileResponse(CompanyProfileRequest):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    is_verified: bool


# ---- assignments & matches ----


class AssignmentCreateRequest(BaseModel):
    description: NonBlankStr = Field(min_length=20, max_length=20000)


class AssignmentRefineRequest(BaseModel):
    answer: NonBlankStr = Field(min_length=1, max_length=8000)


class IntakeMessage(BaseModel):
    role: Literal["company", "concierge"]
    content: str


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    raw_description: str
    requirements: AssignmentRequirements
    intake_history: list[IntakeMessage]
    status: AssignmentStatus
    created_at: UTCDatetime


class MatchSpecialistView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    headline: str
    skills: list[SkillInput]
    years_experience: int
    hourly_rate: float | None
    currency: str
    country: str
    remote_preference: RemotePreference
    trust_score: float


class AssignmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirements: AssignmentRequirements
    status: AssignmentStatus


class MatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    specialist_id: uuid.UUID
    score: float
    breakdown: dict[str, float]
    company_decision: Decision
    specialist_decision: Decision
    status: MatchStatus
    specialist: MatchSpecialistView
    assignment: AssignmentBrief


class MatchDecisionRequest(BaseModel):
    decision: Decision = Field(description="accepted or rejected")


# ---- AI interview ----


class InterviewQuestionView(BaseModel):
    question: str
    skill: str
    rationale: str


class TranscriptEntry(BaseModel):
    question: str
    answer: str


class AnswerScoreView(BaseModel):
    question: str
    score: float
    reasoning: str


class AssessmentView(BaseModel):
    """Projected per viewer: the specialist never receives `concerns`,
    `recommendation`, `summary` or the per-question breakdown."""

    overall_score: float
    strengths: list[str] = Field(default_factory=list)
    development_areas: list[str] = Field(default_factory=list)
    concerns: list[str] | None = None
    recommendation: str | None = None
    summary: str | None = None
    per_question: list[AnswerScoreView] | None = None


class InterviewAnswerRequest(BaseModel):
    answer: NonBlankStr = Field(min_length=1, max_length=8000)


class InterviewResponse(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    status: str
    gap_summary: str
    questions: list[InterviewQuestionView]
    transcript: list[TranscriptEntry]
    current_question: InterviewQuestionView | None
    answered_count: int
    total_questions: int
    assessment: AssessmentView | None
    created_at: UTCDatetime


# ---- team building ----


class TeamMemberView(BaseModel):
    specialist: MatchSpecialistView
    score: float
    breakdown: dict[str, float]


class TeamSeatView(BaseModel):
    role_title: str
    seniority: str
    seats: int
    filled: int
    must_have_skills: list[str]
    members: list[TeamMemberView]


class TeamRationaleView(BaseModel):
    role_title: str
    specialist_headline: str
    why: str


class TeamProposalView(BaseModel):
    summary: str
    strengths: list[str]
    gaps: list[str]
    rationale: list[TeamRationaleView]


class TeamResponse(BaseModel):
    assignment_id: uuid.UUID
    seats: list[TeamSeatView]
    unfilled_seats: int
    proposal: TeamProposalView


# ---- contracts ----


class ContractCreateRequest(BaseModel):
    hourly_rate: float = Field(gt=0, le=10000)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    hours_per_week: int = Field(default=40, ge=1, le=80)
    start_date: date
    end_date: date | None = None


class ContractClauseView(BaseModel):
    heading: str
    body: str


class ContractDraftView(BaseModel):
    title: str
    scope_of_work: list[str]
    rate_terms: str
    duration_terms: str
    clauses: list[ContractClauseView]
    governing_law: str
    open_points: list[str]


class ContractResponse(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    status: str
    hourly_rate: float
    currency: str
    hours_per_week: int
    start_date: date
    end_date: date | None
    draft: ContractDraftView
    company_signed: bool
    specialist_signed: bool
    signed_by_me: bool
    created_at: UTCDatetime


# ---- chat ----


class MessageCreateRequest(BaseModel):
    content: NonBlankStr = Field(min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    content: str
    created_at: UTCDatetime


class ConversationResponse(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    counterpart_name: str
    assignment_title: str
    last_message: str | None
    last_message_at: UTCDatetime | None
    created_at: UTCDatetime
