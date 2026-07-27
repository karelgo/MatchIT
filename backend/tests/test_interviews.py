import pytest

from app.ai.llm import FakeChatModel
from app.ai.schemas import (
    AnswerScore,
    InterviewAssessment,
    InterviewPlan,
    InterviewQuestion,
    Recommendation,
)
from app.services.interview import InterviewService, profile_view, skill_gaps
from tests.conftest import auth_headers, create_company, create_specialist, make_requirements
from tests.test_chat import DESCRIPTION

DEFAULT_SKILLS = ("microsoft fabric", "azure", "data warehousing")


def plan_of(*skills: str) -> InterviewPlan:
    """A plan honouring the schema's 3-question minimum."""
    skills = skills or DEFAULT_SKILLS
    return InterviewPlan(
        gap_summary="Fabric migration experience is claimed but not evidenced.",
        questions=[
            InterviewQuestion(
                question=f"Describe a project where you used {skill}.",
                skill=skill,
                rationale=f"The assignment depends on {skill}.",
            )
            for skill in skills
        ],
    )


async def answer_all(client, fake_chat, tokens, match_id, *, answers, assessment):
    """Answer every remaining question, queueing the assessment before the last."""
    state = (
        await client.get(f"/api/v1/matches/{match_id}/interview", headers=auth_headers(tokens))
    ).json()
    remaining = state["total_questions"] - state["answered_count"]
    for index in range(remaining):
        if index == remaining - 1:
            fake_chat.responses.append(assessment)
        response = await client.post(
            f"/api/v1/matches/{match_id}/interview/answer",
            headers=auth_headers(tokens),
            json={"answer": answers[index % len(answers)]},
        )
        assert response.status_code == 200, response.text
    return response.json()


def assessment_of(score: float, recommendation=Recommendation.YES) -> InterviewAssessment:
    return InterviewAssessment(
        overall_score=score,
        per_question=[AnswerScore(question="Q1", score=score, reasoning="Concrete and specific.")],
        strengths=["Deep Fabric migration experience"],
        development_areas=["Could quantify outcomes more"],
        concerns=["No experience at this data volume"],
        recommendation=recommendation,
        summary="Strong hands-on migration background; proceed to a client call.",
    )


# ---- service unit tests ----


def test_skill_gaps_finds_unclaimed_must_haves():
    from tests.test_matching import profile

    requirements = make_requirements()  # must-haves: fabric, azure, data warehousing
    complete = profile()
    assert skill_gaps(requirements, complete) == []

    partial = profile(skills=[{"name": "azure", "level": 9, "years": 8}])
    assert set(skill_gaps(requirements, partial)) == {"microsoft fabric", "data warehousing"}


def test_profile_view_excludes_identity_and_rate():
    from tests.test_matching import profile

    view = profile_view(profile())
    assert "headline" in view and "skills" in view
    for leaked in ("id", "user_id", "hourly_rate", "currency", "city", "country"):
        assert leaked not in view, f"{leaked} must not reach the interviewer prompt"


async def test_plan_prompt_carries_the_gaps():
    from tests.test_matching import profile

    chat = FakeChatModel(responses=[plan_of()])
    service = InterviewService(chat)
    partial = profile(skills=[{"name": "azure", "level": 9, "years": 8}])
    await service.plan(make_requirements(), partial)

    prompt = chat.calls[0]["user"]
    assert "unproven_must_have_skills" in prompt
    assert "microsoft fabric" in prompt
    assert "data warehousing" in prompt


# ---- API tests ----


async def start_interview(client, fake_chat, *, company_email: str, skills=DEFAULT_SKILLS):
    """Create a match and open its interview. Returns (specialist, company, match, interview)."""
    specialist_tokens, _ = await create_specialist(client)
    company_tokens = await create_company(client, email=company_email)
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    match = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()[0]

    fake_chat.responses.append(plan_of(*skills))
    created = await client.post(
        f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
    )
    assert created.status_code == 200, created.text
    return specialist_tokens, company_tokens, match, created.json()


async def test_full_interview_loop_scores_and_updates_trust(client, fake_chat):
    specialist_tokens, company_tokens, match, interview = await start_interview(
        client, fake_chat, company_email="iv-hm@example.com"
    )
    assert interview["status"] == "in_progress"
    assert interview["total_questions"] == 3
    assert interview["answered_count"] == 0
    assert interview["current_question"]["skill"] == "microsoft fabric"
    assert interview["assessment"] is None

    first = await client.post(
        f"/api/v1/matches/{match['id']}/interview/answer",
        headers=auth_headers(specialist_tokens),
        json={"answer": "I led a 40TB warehouse migration onto Fabric over eight months."},
    )
    assert first.status_code == 200, first.text
    assert first.json()["answered_count"] == 1
    # the interview advances to the next question, and does not score early
    assert first.json()["current_question"]["skill"] == "azure"
    assert first.json()["assessment"] is None

    body = await answer_all(
        client,
        fake_chat,
        specialist_tokens,
        match["id"],
        answers=["Eight years on Azure — Synapse, Data Factory and Purview in production."],
        assessment=assessment_of(0.86),
    )
    assert body["status"] == "completed"
    assert body["answered_count"] == 3
    assert body["current_question"] is None
    assert body["assessment"]["overall_score"] == 0.86
    assert len(body["transcript"]) == 3
    assert body["transcript"][0]["answer"].startswith("I led a 40TB")

    # the assessor saw the whole transcript
    assess_prompt = fake_chat.calls[-1]["user"]
    assert "40TB" in assess_prompt
    assert "Purview" in assess_prompt

    # the interview score now moves the specialist's trust score off zero
    profile = (
        await client.get("/api/v1/specialists/me", headers=auth_headers(specialist_tokens))
    ).json()
    assert profile["trust_score"] > 0
    assert profile["trust_breakdown"]["interview_score"] == 0.86


async def test_specialist_never_sees_concerns_or_recommendation(client, fake_chat):
    specialist_tokens, company_tokens, match, _ = await start_interview(
        client, fake_chat, company_email="iv-hm2@example.com"
    )
    specialist_view = await answer_all(
        client,
        fake_chat,
        specialist_tokens,
        match["id"],
        answers=["I have read about Fabric but not used it."],
        assessment=assessment_of(0.4, Recommendation.NO),
    )

    assessment = specialist_view["assessment"]
    assert assessment["overall_score"] == 0.4
    assert assessment["development_areas"]  # constructive feedback is shared
    assert assessment["concerns"] is None
    assert assessment["recommendation"] is None
    assert assessment["summary"] is None
    assert assessment["per_question"] is None

    company_view = (
        await client.get(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
        )
    ).json()
    company_assessment = company_view["assessment"]
    assert company_assessment["recommendation"] == "no"
    assert company_assessment["concerns"]
    assert company_assessment["summary"]
    assert company_assessment["per_question"]


async def test_start_is_idempotent(client, fake_chat):
    _, company_tokens, match, first = await start_interview(
        client, fake_chat, company_email="iv-hm3@example.com"
    )
    # no new plan queued: a second call must reuse the stored interview
    again = await client.post(
        f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
    )
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]


async def test_company_cannot_answer_and_outsider_cannot_see(client, fake_chat):
    _, company_tokens, match, _ = await start_interview(
        client, fake_chat, company_email="iv-hm4@example.com"
    )
    company_answer = await client.post(
        f"/api/v1/matches/{match['id']}/interview/answer",
        headers=auth_headers(company_tokens),
        json={"answer": "answering on their behalf"},
    )
    assert company_answer.status_code == 403

    outsider = await create_company(client, email="iv-outsider@example.com")
    # not-a-party is 404, so match existence does not leak
    assert (
        await client.get(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(outsider)
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(outsider)
        )
    ).status_code == 404


async def test_answering_completed_interview_conflicts(client, fake_chat):
    specialist_tokens, _, match, _ = await start_interview(
        client, fake_chat, company_email="iv-hm5@example.com"
    )
    done = await answer_all(
        client,
        fake_chat,
        specialist_tokens,
        match["id"],
        answers=["Yes, extensively — I ran that migration end to end."],
        assessment=assessment_of(0.7),
    )
    assert done["status"] == "completed"

    extra = await client.post(
        f"/api/v1/matches/{match['id']}/interview/answer",
        headers=auth_headers(specialist_tokens),
        json={"answer": "one more thought"},
    )
    assert extra.status_code == 409


async def test_interview_missing_until_started(client, fake_chat):
    specialist_tokens, _ = await create_specialist(client)
    company_tokens = await create_company(client, email="iv-hm6@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    match = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()[0]

    assert (
        await client.get(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(specialist_tokens)
        )
    ).status_code == 404


@pytest.mark.parametrize("bad_answer", ["", " " * 5])
async def test_blank_answers_rejected(client, fake_chat, bad_answer):
    specialist_tokens, _, match, _ = await start_interview(
        client, fake_chat, company_email=f"iv-blank{len(bad_answer)}@example.com"
    )
    response = await client.post(
        f"/api/v1/matches/{match['id']}/interview/answer",
        headers=auth_headers(specialist_tokens),
        json={"answer": bad_answer},
    )
    assert response.status_code == 422
