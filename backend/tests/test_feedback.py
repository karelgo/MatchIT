"""Specialist-facing match feedback: honest, specific, and never a model call."""

from tests.conftest import auth_headers, create_company, create_specialist, make_requirements
from tests.test_chat import DESCRIPTION, make_mutual_match
from tests.test_interviews import answer_all, assessment_of, plan_of


async def _rejected_match(client, fake_chat, *, prefix: str, **specialist_kwargs):
    """A candidate the company looked at and passed on."""
    specialist_tokens, _ = await create_specialist(
        client, email=f"{prefix}-spec@example.com", **specialist_kwargs
    )
    company_tokens = await create_company(client, email=f"{prefix}-hm@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    matches = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()
    await client.post(
        f"/api/v1/matches/{matches[0]['id']}/decision",
        headers=auth_headers(company_tokens),
        json={"decision": "rejected"},
    )
    return specialist_tokens, company_tokens, matches[0]


async def _feedback(client, tokens, match_id) -> dict:
    response = await client.get(
        f"/api/v1/matches/{match_id}/feedback", headers=auth_headers(tokens)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_feedback_names_the_missing_must_have_skills(client, fake_chat):
    """The commonest real reason, said plainly, with the skills listed."""
    specialist_tokens, _, match = await _rejected_match(
        client,
        fake_chat,
        prefix="fb-skills",
        skills=[{"name": "azure", "level": 7, "years": 4}],
    )
    body = await _feedback(client, specialist_tokens, match["id"])

    assert body["outcome"] == "not_selected"
    skills = next(f for f in body["cost_you_most"] if f["component"] == "skills")
    assert "microsoft fabric" in skills["what_happened"]
    assert "data warehousing" in skills["what_happened"]
    assert "2 of 3 must-have skills" in skills["what_happened"]
    assert "import your CV" in skills["what_would_help"]


async def test_factors_are_ordered_by_what_actually_cost_the_most(client, fake_chat):
    specialist_tokens, _, match = await _rejected_match(
        client,
        fake_chat,
        prefix="fb-order",
        skills=[{"name": "azure", "level": 7, "years": 4}],
        hourly_rate=400,
    )
    body = await _feedback(client, specialist_tokens, match["id"])

    losses = [factor["points_lost"] for factor in body["cost_you_most"]]
    assert losses == sorted(losses, reverse=True)
    for factor in body["cost_you_most"]:
        assert factor["points_lost"] > 0
        # points lost is exactly the weight not earned on that component
        assert abs(factor["points_lost"] - factor["weight"] * (1 - factor["score"])) < 1e-4


async def test_an_over_budget_rate_is_explained_with_both_numbers(client, fake_chat):
    specialist_tokens, _, match = await _rejected_match(
        client, fake_chat, prefix="fb-rate", hourly_rate=260
    )
    body = await _feedback(client, specialist_tokens, match["id"])

    rate = next(f for f in body["cost_you_most"] if f["component"] == "rate")
    assert "260" in rate["what_happened"] and "130" in rate["what_happened"]
    assert "100%" in rate["what_happened"]
    assert "priced below it" in rate["what_would_help"]


async def test_a_missing_working_language_is_named(client, fake_chat):
    specialist_tokens, _, match = await _rejected_match(
        client, fake_chat, prefix="fb-lang", languages=["de"]
    )
    body = await _feedback(client, specialist_tokens, match["id"])

    language = next(f for f in body["cost_you_most"] if f["component"] == "language")
    assert "en" in language["what_happened"]


async def test_strong_components_are_reported_too(client, fake_chat):
    """Feedback that only lists faults is not feedback."""
    specialist_tokens, _, match = await _rejected_match(client, fake_chat, prefix="fb-good")
    body = await _feedback(client, specialist_tokens, match["id"])

    assert body["worked_in_your_favour"]
    for factor in body["worked_in_your_favour"]:
        assert factor["score"] >= 0.8
    skills = next(f for f in body["worked_in_your_favour"] if f["component"] == "skills")
    assert "every must-have skill" in skills["what_happened"]


async def test_rank_travels_with_the_size_of_the_field(client, fake_chat):
    specialist_tokens, _, match = await _rejected_match(client, fake_chat, prefix="fb-rank")
    body = await _feedback(client, specialist_tokens, match["id"])

    assert body["rank"] == 1
    assert body["candidates_scored"] == 1
    assert 0.0 <= body["total_score"] <= 1.0


async def test_feedback_is_withheld_until_the_company_decides(client, fake_chat):
    specialist_tokens, _ = await create_specialist(client, email="fb-pending@example.com")
    company_tokens = await create_company(client, email="fb-pending-hm@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    matches = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/matches",
            headers=auth_headers(company_tokens),
        )
    ).json()

    response = await client.get(
        f"/api/v1/matches/{matches[0]['id']}/feedback", headers=auth_headers(specialist_tokens)
    )
    assert response.status_code == 409
    assert "not decided" in response.json()["detail"]


async def test_the_company_does_not_receive_the_specialists_feedback(client, fake_chat):
    _, company_tokens, match = await _rejected_match(client, fake_chat, prefix="fb-hm")
    response = await client.get(
        f"/api/v1/matches/{match['id']}/feedback", headers=auth_headers(company_tokens)
    )
    assert response.status_code == 403


async def test_interview_feedback_is_constructive_only(client, fake_chat):
    """Concerns are in the transparency report, not in the coaching summary."""
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="fb-int-hm@example.com"
    )
    fake_chat.responses.append(plan_of())
    await client.post(
        f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
    )
    await answer_all(
        client,
        fake_chat,
        specialist_tokens,
        match["id"],
        answers=["A specific answer about a real migration."],
        assessment=assessment_of(0.7),
    )

    body = await _feedback(client, specialist_tokens, match["id"])
    assert body["outcome"] == "matched"
    assert body["interview_score"] == 0.7
    assert body["interview_strengths"] == ["Deep Fabric migration experience"]
    assert body["interview_development_areas"] == ["Could quantify outcomes more"]
    assert "No experience at this data volume" not in str(body)


async def test_history_lists_settled_matches_and_the_inbox_does_not(client, fake_chat):
    """The inbox is what is still open; history is what closed and why."""
    specialist_tokens, _, match = await _rejected_match(client, fake_chat, prefix="fb-hist")

    inbox = (
        await client.get("/api/v1/matches/inbox", headers=auth_headers(specialist_tokens))
    ).json()
    assert inbox == []

    history = (
        await client.get("/api/v1/matches/history", headers=auth_headers(specialist_tokens))
    ).json()
    assert [entry["id"] for entry in history] == [match["id"]]
    assert history[0]["company_decision"] == "rejected"


async def test_history_excludes_matches_nobody_has_decided(client, fake_chat):
    specialist_tokens, _ = await create_specialist(client, email="fb-open@example.com")
    company_tokens = await create_company(client, email="fb-open-hm@example.com")
    fake_chat.responses.append(make_requirements())
    assignment = (
        await client.post(
            "/api/v1/assignments",
            headers=auth_headers(company_tokens),
            json={"description": DESCRIPTION},
        )
    ).json()
    await client.post(
        f"/api/v1/assignments/{assignment['id']}/matches", headers=auth_headers(company_tokens)
    )

    history = (
        await client.get("/api/v1/matches/history", headers=auth_headers(specialist_tokens))
    ).json()
    assert history == []


async def test_history_is_specialist_side_only(client, fake_chat):
    _, company_tokens, _ = await _rejected_match(client, fake_chat, prefix="fb-hist-hm")
    response = await client.get(
        "/api/v1/matches/history", headers=auth_headers(company_tokens)
    )
    assert response.status_code == 403


async def test_feedback_costs_no_model_call(client, fake_chat):
    """Every rejected candidate gets this, so it must never cost anything."""
    specialist_tokens, _, match = await _rejected_match(client, fake_chat, prefix="fb-free")
    before = len(fake_chat.calls)
    await _feedback(client, specialist_tokens, match["id"])
    await _feedback(client, specialist_tokens, match["id"])
    assert len(fake_chat.calls) == before
