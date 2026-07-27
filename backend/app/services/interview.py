"""AI interview agent: plan questions from profile gaps, then score the answers."""

import json

from app.ai.llm import ChatModel
from app.ai.prompts import INTERVIEW_ASSESSMENT_SYSTEM_PROMPT, INTERVIEW_PLAN_SYSTEM_PROMPT
from app.ai.schemas import AssignmentRequirements, InterviewAssessment, InterviewPlan
from app.models import SpecialistProfile


class InterviewError(Exception):
    """Interview cannot advance (already complete, or no question pending)."""


def profile_view(profile: SpecialistProfile) -> dict:
    """Minimal projection of a profile for prompting.

    Deliberately excludes identifiers, contact details and rate — the interviewer
    has no business knowing who this is or what they cost.
    """
    return {
        "headline": profile.headline,
        "bio": profile.bio,
        "years_experience": profile.years_experience,
        "skills": [
            {"name": s["name"], "level": s.get("level")} for s in profile.skills
        ],
        "certifications": profile.certifications,
        "languages": profile.languages,
    }


def skill_gaps(requirements: AssignmentRequirements, profile: SpecialistProfile) -> list[str]:
    """Must-have skills the profile does not claim at all — the riskiest unknowns."""
    must, _ = requirements.all_skills()
    claimed = {s["name"].lower() for s in profile.skills}
    return [skill for skill in must if skill not in claimed]


def _assignment_view(requirements: AssignmentRequirements) -> dict:
    must, nice = requirements.all_skills()
    return {
        "summary": requirements.summary,
        "roles": [
            {"title": r.title, "seniority": r.seniority, "count": r.count}
            for r in requirements.roles
        ],
        "must_have_skills": must,
        "nice_to_have_skills": nice,
        "industry": requirements.industry,
    }


class InterviewService:
    def __init__(self, chat_model: ChatModel):
        self._chat = chat_model

    async def plan(
        self, requirements: AssignmentRequirements, profile: SpecialistProfile
    ) -> InterviewPlan:
        payload = {
            "assignment": _assignment_view(requirements),
            "specialist": profile_view(profile),
            "unproven_must_have_skills": skill_gaps(requirements, profile),
        }
        return await self._chat.complete_structured(
            system=INTERVIEW_PLAN_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            schema=InterviewPlan,
        )

    async def assess(
        self,
        requirements: AssignmentRequirements,
        profile: SpecialistProfile,
        transcript: list[dict],
    ) -> InterviewAssessment:
        payload = {
            "assignment": _assignment_view(requirements),
            "specialist": profile_view(profile),
            "transcript": transcript,
        }
        return await self._chat.complete_structured(
            system=INTERVIEW_ASSESSMENT_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            schema=InterviewAssessment,
            max_tokens=3072,
        )
