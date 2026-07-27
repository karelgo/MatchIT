import uuid

from app.ai.embeddings import FakeEmbeddingModel
from app.ai.llm import FakeChatModel
from app.ai.schemas import (
    AssignmentRequirements,
    RoleRequirement,
    TeamMemberRationale,
    TeamProposal,
)
from app.services.matching import MatchingEngine
from app.services.team import TeamBuilderService, role_scoped_requirements
from app.services.vector import InMemoryVectorIndex
from tests.conftest import auth_headers, create_company, create_specialist, make_requirements
from tests.test_chat import DESCRIPTION
from tests.test_matching import profile

TWO_ROLES = AssignmentRequirements(
    summary="Migrate the warehouse to Fabric and run the delivery.",
    roles=[
        RoleRequirement(
            title="Microsoft Fabric Architect",
            count=2,
            seniority="senior",
            must_have_skills=["microsoft fabric", "azure"],
        ),
        RoleRequirement(
            title="Scrum Master",
            count=1,
            seniority="medior",
            must_have_skills=["scrum", "agile coaching"],
        ),
    ],
    languages=["en"],
)


def proposal_of(gaps: list[str] | None = None) -> TeamProposal:
    return TeamProposal(
        summary="Two architects and a delivery lead cover the migration end to end.",
        strengths=["Deep Fabric and Azure coverage"],
        gaps=gaps if gaps is not None else [],
        rationale=[
            TeamMemberRationale(
                role_title="Microsoft Fabric Architect",
                specialist_headline="Azure data architect",
                why="Has run a comparable migration.",
            )
        ],
    )


def builder(chat: FakeChatModel) -> TeamBuilderService:
    engine = MatchingEngine(FakeEmbeddingModel(), InMemoryVectorIndex())
    return TeamBuilderService(chat, engine)


# ---- unit ----


def test_role_scoping_keeps_engagement_constraints_but_narrows_skills():
    scoped = role_scoped_requirements(TWO_ROLES, TWO_ROLES.roles[1])
    assert [r.title for r in scoped.roles] == ["Scrum Master"]
    must, _ = scoped.all_skills()
    assert set(must) == {"scrum", "agile coaching"}
    # engagement-level constraints survive the narrowing
    assert scoped.languages == ["en"]
    assert scoped.summary == TWO_ROLES.summary


async def test_allocation_fills_each_seat_without_reusing_anyone():
    chat = FakeChatModel()
    service = builder(chat)
    architects = [
        profile(headline="Azure data architect A"),
        profile(headline="Azure data architect B"),
        profile(headline="Azure data architect C"),
    ]
    scrum = profile(
        headline="Agile delivery lead",
        bio="Scrum and agile coaching",
        skills=[
            {"name": "scrum", "level": 9, "years": 7},
            {"name": "agile coaching", "level": 8, "years": 6},
        ],
    )
    for candidate in [*architects, scrum]:
        await service._engine.index_specialist(candidate)

    plan = await service.allocate(TWO_ROLES, [*architects, scrum])

    assert [a.role.title for a in plan.allocations] == [
        "Microsoft Fabric Architect",
        "Scrum Master",
    ]
    assert len(plan.allocations[0].members) == 2, "two seats must be filled"
    assert len(plan.allocations[1].members) == 1
    assert plan.unfilled_seats == 0

    allocated = [m.profile.id for a in plan.allocations for m in a.members]
    assert len(allocated) == len(set(allocated)), "nobody may occupy two seats"

    # the scrum seat went to the scrum specialist, not a third architect
    assert plan.allocations[1].members[0].profile.id == scrum.id


async def test_scarce_role_is_filled_before_a_broad_one_takes_its_only_candidate():
    """The one Scrum specialist must not be consumed by the architect seats."""
    chat = FakeChatModel()
    service = builder(chat)
    generalist = profile(
        headline="Architect who also runs scrum",
        skills=[
            {"name": "microsoft fabric", "level": 9, "years": 3},
            {"name": "azure", "level": 9, "years": 8},
            {"name": "scrum", "level": 7, "years": 4},
            {"name": "agile coaching", "level": 7, "years": 4},
        ],
    )
    architect = profile(headline="Pure Fabric architect")
    for candidate in (generalist, architect):
        await service._engine.index_specialist(candidate)

    one_each = TWO_ROLES.model_copy(
        update={
            "roles": [
                TWO_ROLES.roles[0].model_copy(update={"count": 1}),
                TWO_ROLES.roles[1],
            ]
        }
    )
    plan = await service.allocate(one_each, [generalist, architect])
    assert plan.unfilled_seats == 0
    assert plan.allocations[1].members[0].profile.id == generalist.id
    assert plan.allocations[0].members[0].profile.id == architect.id


async def test_unfilled_seats_are_reported_not_hidden():
    """A seat must stay empty rather than be filled by someone who cannot do it.

    The lone architect covers none of the Scrum role's must-have skills; padding
    the team with them would disguise a gap as a hire.
    """
    chat = FakeChatModel()
    service = builder(chat)
    only_one = profile()
    await service._engine.index_specialist(only_one)

    plan = await service.allocate(TWO_ROLES, [only_one])
    assert plan.unfilled_seats == 2  # one architect seat + the scrum seat
    assert not plan.allocations[1].is_complete
    assert plan.allocations[1].members == [], "unfit candidate must not take the seat"


async def test_weak_candidates_are_never_allocated():
    chat = FakeChatModel()
    service = builder(chat)
    unrelated = profile(
        headline="React frontend developer",
        bio="Design systems",
        skills=[{"name": "react", "level": 9, "years": 6}],
    )
    await service._engine.index_specialist(unrelated)

    plan = await service.allocate(TWO_ROLES, [unrelated])
    assert plan.unfilled_seats == 3, "no seat should be filled by an unrelated profile"
    assert all(a.members == [] for a in plan.allocations)


async def test_review_prompt_reports_unfilled_seats_to_the_agent():
    chat = FakeChatModel(responses=[proposal_of(gaps=["Scrum Master seat unfilled"])])
    service = builder(chat)
    only_one = profile()
    await service._engine.index_specialist(only_one)
    plan = await service.allocate(TWO_ROLES, [only_one])

    proposal = await service.review(TWO_ROLES, plan)
    prompt = chat.calls[0]["user"]
    assert "unfilled_seats" in prompt
    assert "Scrum Master" in prompt
    assert proposal.gaps


# ---- API ----


async def test_team_endpoint_returns_seats_and_proposal(client, fake_chat):
    await create_specialist(client, email="team-a@example.com")
    await create_specialist(client, email="team-b@example.com")
    await create_specialist(
        client,
        email="team-scrum@example.com",
        skills=[
            {"name": "scrum", "level": 9, "years": 7},
            {"name": "agile coaching", "level": 8, "years": 6},
        ],
    )
    company_tokens = await create_company(client, email="team-hm@example.com")

    fake_chat.responses.append(make_requirements(roles=TWO_ROLES.roles))
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()

    fake_chat.responses.append(proposal_of())
    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/team", headers=auth_headers(company_tokens)
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert [s["role_title"] for s in body["seats"]] == [
        "Microsoft Fabric Architect",
        "Scrum Master",
    ]
    assert body["seats"][0]["seats"] == 2
    assert body["seats"][0]["filled"] == 2
    assert body["seats"][1]["filled"] == 1
    assert body["unfilled_seats"] == 0
    assert body["proposal"]["summary"]

    everyone = [m["specialist"]["id"] for s in body["seats"] for m in s["members"]]
    assert len(everyone) == len(set(everyone)), "a specialist appeared in two seats"
    assert all("skills" in m["specialist"] for s in body["seats"] for m in s["members"])


async def test_team_endpoint_is_company_scoped(client, fake_chat):
    company_tokens = await create_company(client, email="team-owner@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()

    other = await create_company(client, email="team-other@example.com")
    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/team", headers=auth_headers(other)
    )
    assert response.status_code == 404
    assert uuid.UUID(assignment["id"])
