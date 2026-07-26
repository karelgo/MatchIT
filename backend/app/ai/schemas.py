"""Structured output contracts for AI capabilities.

These Pydantic models double as JSON schemas for constrained LLM output and as
the validated shape persisted on domain entities.
"""

from datetime import date

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
