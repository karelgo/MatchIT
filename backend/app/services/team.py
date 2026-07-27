"""Team builder: allocate specialists to the seats a multi-role assignment needs.

The matching engine ranks people against a whole assignment. A company asking for
"two Fabric architects and a Scrum master" does not want three people who all look
like the assignment on average — it wants each seat filled by someone who fits
*that seat*, with nobody counted twice.
"""

import json
from dataclasses import dataclass, field

from app.ai.llm import ChatModel
from app.ai.prompts import TEAM_BUILDER_SYSTEM_PROMPT
from app.ai.schemas import AssignmentRequirements, RoleRequirement, TeamProposal
from app.models import SpecialistProfile
from app.services.matching import MatchingEngine, RankedCandidate


def role_scoped_requirements(
    requirements: AssignmentRequirements, role: RoleRequirement
) -> AssignmentRequirements:
    """The assignment as it looks for one role only.

    Constraints that belong to the engagement (budget, location, languages,
    dates) are kept; the skill profile narrows to this role's.
    """
    return requirements.model_copy(update={"roles": [role]})


# A seat left visibly empty is more useful than a seat filled by someone who
# cannot do the job: the first is a gap the company can act on, the second is a
# gap disguised as a team. A candidate must therefore cover at least one of the
# role's must-have skills and clear an overall floor to take a seat.
MIN_SEAT_SCORE = 0.35


def is_viable(candidate: RankedCandidate) -> bool:
    return candidate.breakdown.get("skills", 0.0) > 0.0 and candidate.score >= MIN_SEAT_SCORE


@dataclass
class SeatAllocation:
    role: RoleRequirement
    members: list[RankedCandidate] = field(default_factory=list)

    @property
    def seats(self) -> int:
        return self.role.count

    @property
    def is_complete(self) -> bool:
        return len(self.members) >= self.seats


@dataclass
class TeamPlan:
    allocations: list[SeatAllocation]
    proposal: TeamProposal | None = None

    @property
    def unfilled_seats(self) -> int:
        return sum(a.seats - len(a.members) for a in self.allocations)


class TeamBuilderService:
    def __init__(self, chat_model: ChatModel, engine: MatchingEngine):
        self._chat = chat_model
        self._engine = engine

    async def allocate(
        self,
        requirements: AssignmentRequirements,
        candidates: list[SpecialistProfile],
    ) -> TeamPlan:
        """Fill each role's seats, never assigning the same person twice.

        Roles are filled scarcest-first (fewest strong candidates), so a role with
        one viable specialist is not left empty because a broader role took them.
        """
        ranked_by_role: dict[int, list[RankedCandidate]] = {}
        for index, role in enumerate(requirements.roles):
            scoped = role_scoped_requirements(requirements, role)
            ranked_by_role[index] = await self._engine.rank(scoped, candidates)

        # Scarcest role first, so a role with one viable specialist is not left
        # empty because a broader role took them.
        order = sorted(
            range(len(requirements.roles)),
            key=lambda i: sum(1 for c in ranked_by_role[i] if is_viable(c)),
        )

        taken: set = set()
        allocations = {
            i: SeatAllocation(role=role) for i, role in enumerate(requirements.roles)
        }
        for index in order:
            for candidate in ranked_by_role[index]:
                if allocations[index].is_complete:
                    break
                if candidate.profile.id in taken or not is_viable(candidate):
                    continue
                taken.add(candidate.profile.id)
                allocations[index].members.append(candidate)

        return TeamPlan(allocations=[allocations[i] for i in range(len(requirements.roles))])

    async def review(self, requirements: AssignmentRequirements, plan: TeamPlan) -> TeamProposal:
        payload = {
            "assignment": requirements.summary,
            "roles": [
                {
                    "title": allocation.role.title,
                    "seniority": allocation.role.seniority,
                    "seats": allocation.seats,
                    "must_have_skills": allocation.role.must_have_skills,
                    "allocated": [
                        {
                            "headline": member.profile.headline,
                            "skills": [s["name"] for s in member.profile.skills],
                            "years_experience": member.profile.years_experience,
                            "score": round(member.score, 3),
                        }
                        for member in allocation.members
                    ],
                    "unfilled_seats": allocation.seats - len(allocation.members),
                }
                for allocation in plan.allocations
            ],
        }
        return await self._chat.complete_structured(
            system=TEAM_BUILDER_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            schema=TeamProposal,
            max_tokens=3072,
        )

    async def build(
        self, requirements: AssignmentRequirements, candidates: list[SpecialistProfile]
    ) -> TeamPlan:
        plan = await self.allocate(requirements, candidates)
        plan.proposal = await self.review(requirements, plan)
        return plan
