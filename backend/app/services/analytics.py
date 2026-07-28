"""Platform analytics for the admin portal."""

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Assignment,
    Contract,
    ContractStatus,
    Decision,
    Interview,
    InterviewStatus,
    Match,
    MatchStatus,
    Message,
    SpecialistProfile,
    User,
)

# Cohorts smaller than this are reported but never judged: an adverse-impact
# ratio computed over three people is noise wearing a statistic's clothes.
MIN_COHORT_SIZE = 5

# The classic adverse-impact threshold (the EEOC "four-fifths rule"): a cohort
# selected at less than 80% of the best-performing cohort's rate is flagged.
FOUR_FIFTHS = 0.8


@dataclass
class Funnel:
    """The core loop, stage by stage. Each number is a count of distinct rows."""

    specialists: int
    companies: int
    assignments: int
    matches_suggested: int
    matches_mutual: int
    interviews_completed: int
    contracts_active: int

    def conversion_rates(self) -> dict[str, float]:
        def ratio(numerator: int, denominator: int) -> float:
            return round(numerator / denominator, 4) if denominator else 0.0

        return {
            "suggested_to_mutual": ratio(self.matches_mutual, self.matches_suggested),
            "mutual_to_interviewed": ratio(self.interviews_completed, self.matches_mutual),
            "mutual_to_contracted": ratio(self.contracts_active, self.matches_mutual),
            "assignment_to_contract": ratio(self.contracts_active, self.assignments),
        }


@dataclass
class Cohort:
    """Outcomes for one group of specialists along one observable dimension."""

    cohort: str
    matches: int = 0
    decided: int = 0
    selected: int = 0
    match_scores: list[float] = field(default_factory=list)
    interview_scores: list[float] = field(default_factory=list)

    @property
    def selection_rate(self) -> float | None:
        return round(self.selected / self.decided, 4) if self.decided else None

    @property
    def sufficient_data(self) -> bool:
        return self.decided >= MIN_COHORT_SIZE

    def _mean(self, values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def view(self, best_rate: float | None) -> dict:
        rate = self.selection_rate
        impact = (
            round(rate / best_rate, 4)
            if rate is not None and best_rate not in (None, 0)
            else None
        )
        return {
            "cohort": self.cohort,
            "matches": self.matches,
            "decided": self.decided,
            "selected": self.selected,
            "selection_rate": rate,
            "impact_ratio": impact,
            "mean_match_score": self._mean(self.match_scores),
            "mean_interview_score": self._mean(self.interview_scores),
            "sufficient_data": self.sufficient_data,
        }


def _experience_band(profile: SpecialistProfile) -> str:
    years = profile.years_experience
    bands = ((3, "0-2 years"), (6, "3-5 years"), (11, "6-10 years"), (21, "11-20 years"))
    for ceiling, label in bands:
        if years < ceiling:
            return label
    return "20+ years"


# The dimensions MatchIT can actually monitor, and why each one is here.
#
# MatchIT never collects age, gender, ethnicity, nationality, health or religion,
# which is the right design and also means it cannot measure disparity against
# them directly. What it can do is watch the observable attributes that correlate
# with them and are themselves grounds for discrimination in EU staffing: years of
# experience (the standard age proxy), country, and working language. Watching a
# proxy is weaker than watching the real thing and stronger than watching nothing.
BIAS_DIMENSIONS: dict[str, tuple[str, Callable[[SpecialistProfile], str]]] = {
    "experience_band": (
        "Years of experience, banded. The closest observable proxy for age, which is "
        "the most common ground of recruitment discrimination in the EU.",
        _experience_band,
    ),
    "country": (
        "Country of residence, a proxy for nationality in a cross-border market.",
        lambda profile: profile.country.upper(),
    ),
    "works_in_dutch": (
        "Whether the specialist lists Dutch. Language requirements are a recognised "
        "route to indirect nationality discrimination in the Dutch market.",
        lambda profile: "speaks nl" if "nl" in
        {code.lower() for code in profile.languages} else "does not speak nl",
    ),
    "remote_preference": (
        "Remote, hybrid or on-site. Watched because remote-only preferences "
        "correlate with carer responsibilities and disability.",
        lambda profile: profile.remote_preference.value,
    ),
}

_BIAS_NOTES = (
    "MatchIT does not collect age, gender, ethnicity, nationality, health or religion, "
    "so disparity cannot be measured against them directly. The dimensions below are "
    "observable proxies, and a flag on one is a prompt to investigate, never a finding.",
    f"A cohort is judged only once at least {MIN_COHORT_SIZE} of its members have been "
    "decided on. Smaller cohorts are shown with their numbers and left unflagged.",
    f"`impact_ratio` compares a cohort's selection rate with the best-performing "
    f"cohort in the same dimension. Below {FOUR_FIFTHS:.0%} — the four-fifths rule — "
    "the cohort is flagged.",
    "Selection rate counts company decisions only. A specialist declining an "
    "opportunity is their choice and is not disparity.",
)


class AnalyticsService:
    async def bias(self, db: AsyncSession) -> dict:
        """Outcome disparity across the cohorts MatchIT can observe.

        The EU AI Act asks deployers of high-risk recruitment AI for continuous
        monitoring rather than a one-off assessment, so this is a dashboard query
        and not a periodic report someone has to remember to run.
        """
        rows = await db.scalars(
            select(Match).options(selectinload(Match.specialist))
        )
        matches = list(rows)
        interview_scores = dict(
            (match_id, score)
            for match_id, score in await db.execute(
                select(Interview.match_id, Interview.score).where(Interview.score.is_not(None))
            )
        )

        dimensions = []
        for name, (description, classify) in BIAS_DIMENSIONS.items():
            cohorts: dict[str, Cohort] = {}
            for match in matches:
                key = classify(match.specialist)
                cohort = cohorts.setdefault(key, Cohort(cohort=key))
                cohort.matches += 1
                cohort.match_scores.append(float(match.score))
                if (score := interview_scores.get(match.id)) is not None:
                    cohort.interview_scores.append(float(score))
                if match.company_decision != Decision.PENDING:
                    cohort.decided += 1
                    if match.company_decision == Decision.ACCEPTED:
                        cohort.selected += 1

            judged = [c for c in cohorts.values() if c.sufficient_data]
            rates = [c.selection_rate for c in judged if c.selection_rate is not None]
            best = max(rates) if rates else None
            views = [
                cohort.view(best)
                for cohort in sorted(cohorts.values(), key=lambda c: c.cohort)
            ]
            flagged = [
                view["cohort"]
                for view in views
                if view["sufficient_data"]
                and view["impact_ratio"] is not None
                and view["impact_ratio"] < FOUR_FIFTHS
            ]
            dimensions.append(
                {
                    "dimension": name,
                    "description": description,
                    "cohorts": views,
                    "flagged": flagged,
                }
            )

        return {
            "dimensions": dimensions,
            "minimum_cohort_size": MIN_COHORT_SIZE,
            "notes": list(_BIAS_NOTES),
        }

    async def funnel(self, db: AsyncSession) -> Funnel:
        async def count(model, *where) -> int:
            statement = select(func.count()).select_from(model)
            for clause in where:
                statement = statement.where(clause)
            return int(await db.scalar(statement) or 0)

        from app.models import CompanyProfile

        return Funnel(
            specialists=await count(SpecialistProfile),
            companies=await count(CompanyProfile),
            assignments=await count(Assignment),
            matches_suggested=await count(Match),
            matches_mutual=await count(Match, Match.status == MatchStatus.MUTUAL),
            interviews_completed=await count(
                Interview, Interview.status == InterviewStatus.COMPLETED
            ),
            contracts_active=await count(Contract, Contract.status == ContractStatus.ACTIVE),
        )

    async def quality(self, db: AsyncSession) -> dict:
        """Signals about how well matching and interviewing are working."""
        average_match_score = await db.scalar(select(func.avg(Match.score)))
        average_interview_score = await db.scalar(
            select(func.avg(Interview.score)).where(Interview.score.is_not(None))
        )
        average_trust = await db.scalar(select(func.avg(SpecialistProfile.trust_score)))
        messages = int(await db.scalar(select(func.count()).select_from(Message)) or 0)
        return {
            "average_match_score": round(float(average_match_score or 0.0), 4),
            "average_interview_score": round(float(average_interview_score or 0.0), 4),
            "average_trust_score": round(float(average_trust or 0.0), 2),
            "messages_sent": messages,
        }

    async def time_to_contract_hours(self, db: AsyncSession) -> float | None:
        """Median-free mean: assignment created → contract activated.

        Reported in hours because the product promise is "minutes, not weeks" and
        a figure in days would hide the thing worth watching.
        """
        rows = await db.execute(
            select(Assignment.created_at, Contract.created_at)
            .join(Match, Match.assignment_id == Assignment.id)
            .join(Contract, Contract.match_id == Match.id)
            .where(Contract.status == ContractStatus.ACTIVE)
        )
        deltas = [
            (contract_at - assignment_at).total_seconds() / 3600.0
            for assignment_at, contract_at in rows
            if assignment_at and contract_at
        ]
        return round(sum(deltas) / len(deltas), 2) if deltas else None

    async def user_counts(self, db: AsyncSession) -> dict[str, int]:
        rows = await db.execute(select(User.role, func.count()).group_by(User.role))
        return {role.value: int(count) for role, count in rows}
