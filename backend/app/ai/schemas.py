"""Structured output contracts for AI capabilities.

These Pydantic models double as JSON schemas for constrained LLM output and as
the validated shape persisted on domain entities.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class RoleRequirement(BaseModel):
    title: str = Field(description="Role title, e.g. 'Microsoft Fabric Architect'")
    count: int = Field(default=1, ge=1, le=50)
    seniority: str = Field(default="senior", description="junior | medior | senior | principal")
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)


class BudgetRange(BaseModel):
    min_hourly: float | None = Field(default=None, ge=0)
    max_hourly: float | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)


class AssignmentRequirements(BaseModel):
    """Everything the matching engine needs, extracted from natural language."""

    summary: str = Field(description="One-paragraph restatement of the assignment")
    roles: list[RoleRequirement] = Field(min_length=1)
    languages: list[str] = Field(default_factory=list, description="ISO 639-1 codes")
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2, if location-bound")
    city: str | None = None
    remote_allowed: bool = True
    start_date: date | None = None
    duration_weeks: int | None = Field(default=None, ge=1)
    duration_is_estimated: bool = Field(
        default=False, description="True when duration_weeks is an AI market estimate"
    )
    budget: BudgetRange = Field(default_factory=BudgetRange)
    budget_is_estimated: bool = Field(
        default=False, description="True when the budget is an AI market estimate"
    )
    certifications: list[str] = Field(default_factory=list)
    industry: str | None = None
    clarifying_questions: list[str] = Field(
        default_factory=list,
        description="Questions the concierge should ask to close information gaps",
    )

    def all_skills(self) -> tuple[list[str], list[str]]:
        must, nice = [], []
        for role in self.roles:
            must.extend(s.lower() for s in role.must_have_skills)
            nice.extend(s.lower() for s in role.nice_to_have_skills)
        return list(dict.fromkeys(must)), list(dict.fromkeys(nice))


# ---- AI interview ----


class InterviewQuestion(BaseModel):
    question: str = Field(description="The question, addressed directly to the specialist")
    skill: str = Field(description="Canonical skill or competency this probes")
    rationale: str = Field(
        description="Why this matters for THIS assignment — shown to the company"
    )


class InterviewPlan(BaseModel):
    """Questions targeted at what the profile does not already evidence."""

    gap_summary: str = Field(
        description="What the profile leaves unproven against the assignment's must-haves"
    )
    questions: list[InterviewQuestion] = Field(min_length=3, max_length=8)


class AnswerScore(BaseModel):
    question: str
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


class Recommendation(StrEnum):
    STRONG_YES = "strong_yes"
    YES = "yes"
    MAYBE = "maybe"
    NO = "no"


class InterviewAssessment(BaseModel):
    overall_score: float = Field(ge=0.0, le=1.0)
    per_question: list[AnswerScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    development_areas: list[str] = Field(
        default_factory=list, description="Constructive, shown to the specialist"
    )
    concerns: list[str] = Field(
        default_factory=list,
        description="Risks for the hiring manager — not shown to the specialist",
    )
    recommendation: Recommendation
    summary: str = Field(description="Hiring-manager-facing summary of the interview")


# ---- supply-side enrichment ----


class SkillSource(StrEnum):
    SELF_REPORTED = "self_reported"
    CV = "cv"
    GITHUB = "github"
    CERTIFICATION = "certification"
    INTERVIEW = "interview"


class EvidencedSkill(BaseModel):
    name: str = Field(description="Canonical lower-case skill name")
    level: int = Field(ge=0, le=10, description="Demonstrated level, judged from the evidence")
    years: float = Field(default=0, ge=0, le=60)
    evidence: str = Field(description="The specific thing in the source that supports this")


class CVExtraction(BaseModel):
    """Skills and history read out of a CV."""

    headline: str = Field(description="One-line professional headline for this person")
    summary: str = Field(description="Two or three sentences a hiring manager would read")
    years_experience: int = Field(ge=0, le=60)
    skills: list[EvidencedSkill] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list, description="ISO 639-1 codes")


class GitHubExtraction(BaseModel):
    """Skills inferred from public repository activity."""

    summary: str = Field(description="What this developer's public work actually shows")
    skills: list[EvidencedSkill] = Field(default_factory=list)


class CVSection(BaseModel):
    heading: str = Field(description="e.g. 'Core skills', 'Selected work', 'Certifications'")
    bullets: list[str] = Field(min_length=1)


class GeneratedCV(BaseModel):
    """A CV written from the profile's evidence — never beyond it."""

    headline: str
    summary: str = Field(description="Three or four sentences, first person, no clichés")
    sections: list[CVSection] = Field(min_length=2)


# ---- team building ----


class TeamMemberRationale(BaseModel):
    role_title: str
    specialist_headline: str
    why: str = Field(description="Why this person fits this seat, in one or two sentences")


class TeamProposal(BaseModel):
    summary: str = Field(description="How this team covers the assignment, in a short paragraph")
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(
        default_factory=list,
        description="Unfilled seats, thin coverage or key-person risk the company should know",
    )
    rationale: list[TeamMemberRationale] = Field(default_factory=list)


# ---- contracts ----


class ContractClause(BaseModel):
    heading: str
    body: str


class ContractDraft(BaseModel):
    """A draft engagement contract. Always a draft — never legal advice."""

    title: str
    scope_of_work: list[str] = Field(
        min_length=1, description="Concrete deliverables and responsibilities"
    )
    rate_terms: str = Field(description="Rate, invoicing cadence and payment terms in prose")
    duration_terms: str = Field(description="Start, duration, extension and notice in prose")
    clauses: list[ContractClause] = Field(
        min_length=3,
        description="At minimum: intellectual property, confidentiality, termination",
    )
    governing_law: str = Field(description="Jurisdiction, e.g. 'the laws of the Netherlands'")
    open_points: list[str] = Field(
        default_factory=list,
        description="Anything the parties must still decide, or that needs a lawyer's eye",
    )
