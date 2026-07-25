"""Hybrid matching engine: vector recall + explainable deterministic ranking.

Every component score lives in [0, 1]; the final score is a weighted blend and the
full breakdown is persisted so ranking is always explainable.
"""

from dataclasses import dataclass
from datetime import date

from app.ai.embeddings import EmbeddingModel
from app.ai.prompts import ASSIGNMENT_EMBEDDING_TEMPLATE, PROFILE_EMBEDDING_TEMPLATE
from app.ai.schemas import AssignmentRequirements
from app.models import RemotePreference, SpecialistProfile
from app.services.vector import SPECIALISTS_COLLECTION, VectorIndex

WEIGHTS = {
    "skills": 0.40,
    "semantic": 0.25,
    "rate": 0.10,
    "availability": 0.10,
    "location": 0.10,
    "language": 0.05,
}

NICE_TO_HAVE_WEIGHT = 1 / 3


def profile_embedding_text(profile: SpecialistProfile) -> str:
    return PROFILE_EMBEDDING_TEMPLATE.format(
        headline=profile.headline,
        bio=profile.bio,
        skills=", ".join(s["name"] for s in profile.skills),
        years_experience=profile.years_experience,
        certifications=", ".join(profile.certifications),
        languages=", ".join(profile.languages),
    )


def assignment_embedding_text(requirements: AssignmentRequirements) -> str:
    must, nice = requirements.all_skills()
    return ASSIGNMENT_EMBEDDING_TEMPLATE.format(
        summary=requirements.summary,
        roles=", ".join(f"{r.count}x {r.title} ({r.seniority})" for r in requirements.roles),
        skills=", ".join(must + nice),
        industry=requirements.industry or "any",
    )


def skill_score(requirements: AssignmentRequirements, profile: SpecialistProfile) -> float:
    must, nice = requirements.all_skills()
    if not must and not nice:
        return 0.5  # nothing to score against: neutral
    profile_skills = {s["name"].lower() for s in profile.skills}
    total = len(must) + NICE_TO_HAVE_WEIGHT * len(nice)
    covered = sum(1.0 for s in must if s in profile_skills) + NICE_TO_HAVE_WEIGHT * sum(
        1.0 for s in nice if s in profile_skills
    )
    return covered / total


def rate_score(requirements: AssignmentRequirements, profile: SpecialistProfile) -> float:
    budget = requirements.budget
    if profile.hourly_rate is None or budget.max_hourly is None:
        return 0.5  # unknown: neutral, resolved by the concierge's clarifying questions
    if profile.hourly_rate <= budget.max_hourly:
        return 1.0
    # linear decay: 50% over budget -> 0
    overage = (profile.hourly_rate - budget.max_hourly) / budget.max_hourly
    return max(0.0, 1.0 - overage * 2.0)


def availability_score(
    requirements: AssignmentRequirements, profile: SpecialistProfile, today: date
) -> float:
    start = requirements.start_date
    available = profile.available_from or today
    if start is None:
        return 1.0 if available <= today else 0.5
    if available <= start:
        return 1.0
    # each week late costs 25%
    weeks_late = (available - start).days / 7.0
    return max(0.0, 1.0 - 0.25 * weeks_late)


def location_score(requirements: AssignmentRequirements, profile: SpecialistProfile) -> float:
    if requirements.remote_allowed:
        return 1.0
    # on-site assignment
    if profile.remote_preference == RemotePreference.REMOTE:
        return 0.0
    if requirements.country and requirements.country.upper() != profile.country.upper():
        return 0.0
    return 1.0 if profile.remote_preference == RemotePreference.ONSITE else 0.8


def language_score(requirements: AssignmentRequirements, profile: SpecialistProfile) -> float:
    required = {code.lower() for code in requirements.languages}
    if not required:
        return 1.0
    spoken = {code.lower() for code in profile.languages}
    return len(required & spoken) / len(required)


@dataclass
class RankedCandidate:
    profile: SpecialistProfile
    score: float
    breakdown: dict[str, float]


class MatchingEngine:
    def __init__(self, embedding_model: EmbeddingModel, vector_index: VectorIndex):
        self._embeddings = embedding_model
        self._index = vector_index

    async def index_specialist(self, profile: SpecialistProfile) -> None:
        [vector] = await self._embeddings.embed([profile_embedding_text(profile)])
        await self._index.upsert(
            SPECIALISTS_COLLECTION,
            profile.id,
            vector,
            {
                "country": profile.country,
                "remote_preference": profile.remote_preference.value,
                "skills": [s["name"] for s in profile.skills][:20],
            },
        )

    async def rank(
        self,
        requirements: AssignmentRequirements,
        candidates: list[SpecialistProfile],
        *,
        today: date | None = None,
    ) -> list[RankedCandidate]:
        """Rank candidate profiles against an assignment.

        Semantic similarity comes from the vector index (candidates are indexed at
        profile save time); the remaining components are deterministic.
        """
        today = today or date.today()
        [assignment_vector] = await self._embeddings.embed(
            [assignment_embedding_text(requirements)]
        )
        hits = await self._index.search(
            SPECIALISTS_COLLECTION, assignment_vector, limit=max(len(candidates), 100)
        )
        semantic_by_id = {hit.id: hit.score for hit in hits}

        ranked = []
        for profile in candidates:
            breakdown = {
                "skills": skill_score(requirements, profile),
                "semantic": max(0.0, min(1.0, semantic_by_id.get(profile.id, 0.0))),
                "rate": rate_score(requirements, profile),
                "availability": availability_score(requirements, profile, today),
                "location": location_score(requirements, profile),
                "language": language_score(requirements, profile),
            }
            score = sum(WEIGHTS[k] * v for k, v in breakdown.items())
            ranked.append(RankedCandidate(profile=profile, score=score, breakdown=breakdown))

        ranked.sort(key=lambda c: c.score, reverse=True)
        return ranked
