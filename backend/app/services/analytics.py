"""Platform analytics for the admin portal."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    Contract,
    ContractStatus,
    Interview,
    InterviewStatus,
    Match,
    MatchStatus,
    Message,
    SpecialistProfile,
    User,
)


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


class AnalyticsService:
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
