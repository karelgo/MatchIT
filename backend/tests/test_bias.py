"""Bias monitoring: outcome disparity across the cohorts MatchIT can observe."""

from app.services.analytics import (
    FOUR_FIFTHS,
    MIN_COHORT_SIZE,
    AnalyticsService,
    Cohort,
    _experience_band,
)
from tests.conftest import auth_headers, create_company, create_specialist, make_requirements
from tests.test_admin import make_admin
from tests.test_chat import DESCRIPTION


def test_experience_bands_are_contiguous_and_cover_everything():
    """A band boundary off by one would silently mis-cohort people."""

    class _Profile:
        def __init__(self, years):
            self.years_experience = years

    assert _experience_band(_Profile(0)) == "0-2 years"
    assert _experience_band(_Profile(2)) == "0-2 years"
    assert _experience_band(_Profile(3)) == "3-5 years"
    assert _experience_band(_Profile(5)) == "3-5 years"
    assert _experience_band(_Profile(6)) == "6-10 years"
    assert _experience_band(_Profile(10)) == "6-10 years"
    assert _experience_band(_Profile(11)) == "11-20 years"
    assert _experience_band(_Profile(20)) == "11-20 years"
    assert _experience_band(_Profile(21)) == "20+ years"


def test_impact_ratio_flags_at_four_fifths():
    """The threshold is the point of the metric; pin it."""
    best = Cohort(cohort="a", decided=10, selected=10)
    assert best.selection_rate == 1.0

    just_over = Cohort(cohort="b", decided=10, selected=8)
    assert just_over.view(1.0)["impact_ratio"] == 0.8
    assert just_over.view(1.0)["impact_ratio"] >= FOUR_FIFTHS

    just_under = Cohort(cohort="c", decided=10, selected=7)
    assert just_under.view(1.0)["impact_ratio"] < FOUR_FIFTHS


def test_a_cohort_too_small_to_judge_is_shown_but_not_flagged():
    small = Cohort(cohort="tiny", decided=MIN_COHORT_SIZE - 1, selected=0)
    assert small.sufficient_data is False
    view = small.view(1.0)
    assert view["selection_rate"] == 0.0  # reported honestly
    assert view["sufficient_data"] is False


def test_an_undecided_cohort_has_no_selection_rate():
    """Zero decisions is not a zero selection rate — that would read as bias."""
    view = Cohort(cohort="new", matches=3).view(1.0)
    assert view["selection_rate"] is None
    assert view["impact_ratio"] is None


async def test_bias_endpoint_reports_every_dimension(client, fake_chat):
    await create_specialist(client, email="bias-a@example.com")
    company_tokens = await create_company(client, email="bias-dim-hm@example.com")
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

    admin = await make_admin(client, email="bias-admin@example.com")
    body = (await client.get("/api/v1/admin/bias", headers=auth_headers(admin))).json()

    names = {dimension["dimension"] for dimension in body["dimensions"]}
    assert names == {"experience_band", "country", "works_in_dutch", "remote_preference"}
    assert body["minimum_cohort_size"] == MIN_COHORT_SIZE
    for dimension in body["dimensions"]:
        assert dimension["description"]
        assert dimension["cohorts"]
        # a single undecided match cannot be evidence of anything
        assert dimension["flagged"] == []


async def test_disparity_between_cohorts_is_flagged(client, fake_chat):
    """Ten Dutch speakers accepted, ten non-Dutch rejected: that must show up."""
    for index in range(MIN_COHORT_SIZE + 1):
        await create_specialist(
            client, email=f"bias-nl-{index}@example.com", languages=["en", "nl"]
        )
        await create_specialist(client, email=f"bias-en-{index}@example.com", languages=["en"])

    company_tokens = await create_company(client, email="bias-flag-hm@example.com")
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

    assert len(matches) == 2 * (MIN_COHORT_SIZE + 1)

    sessionmaker = client._transport.app.state.sessionmaker
    from sqlalchemy import select

    from app.models import SpecialistProfile

    async with sessionmaker() as db:
        dutch = {
            str(profile.id)
            for profile in await db.scalars(select(SpecialistProfile))
            if "nl" in profile.languages
        }

    for match in matches:
        speaks_dutch = match["specialist_id"] in dutch
        await client.post(
            f"/api/v1/matches/{match['id']}/decision",
            headers=auth_headers(company_tokens),
            json={"decision": "accepted" if speaks_dutch else "rejected"},
        )

    admin = await make_admin(client, email="bias-flag-admin@example.com")
    body = (await client.get("/api/v1/admin/bias", headers=auth_headers(admin))).json()
    dimension = next(d for d in body["dimensions"] if d["dimension"] == "works_in_dutch")
    cohorts = {cohort["cohort"]: cohort for cohort in dimension["cohorts"]}

    assert cohorts["speaks nl"]["selection_rate"] == 1.0
    assert cohorts["does not speak nl"]["selection_rate"] == 0.0
    assert cohorts["does not speak nl"]["impact_ratio"] == 0.0
    assert dimension["flagged"] == ["does not speak nl"]


async def test_a_specialist_declining_is_not_counted_as_disparity(client, fake_chat):
    """Selection rate counts company decisions; declining is the person's own choice."""
    specialists = []
    for index in range(MIN_COHORT_SIZE):
        tokens, _ = await create_specialist(client, email=f"bias-dec-{index}@example.com")
        specialists.append(tokens)

    company_tokens = await create_company(client, email="bias-dec-hm@example.com")
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
    for tokens, match in zip(specialists, matches, strict=True):
        await client.post(
            f"/api/v1/matches/{match['id']}/decision",
            headers=auth_headers(tokens),
            json={"decision": "rejected"},
        )

    admin = await make_admin(client, email="bias-dec-admin@example.com")
    body = (await client.get("/api/v1/admin/bias", headers=auth_headers(admin))).json()
    for dimension in body["dimensions"]:
        for cohort in dimension["cohorts"]:
            assert cohort["decided"] == 0
            assert cohort["selection_rate"] is None
        assert dimension["flagged"] == []


async def test_bias_report_states_what_it_cannot_measure(client):
    """A monitoring dashboard that overstates its own reach is worse than none."""
    admin = await make_admin(client, email="bias-notes-admin@example.com")
    body = (await client.get("/api/v1/admin/bias", headers=auth_headers(admin))).json()
    notes = " ".join(body["notes"]).lower()

    assert "does not collect age, gender, ethnicity, nationality" in notes
    assert "proxies" in notes
    assert "four-fifths" in notes


async def test_bias_is_admin_only_and_invisible_to_everyone_else(client):
    tokens, _ = await create_specialist(client, email="bias-nosy@example.com")
    response = await client.get("/api/v1/admin/bias", headers=auth_headers(tokens))
    assert response.status_code == 404  # not 403: the surface does not confirm itself


async def test_bias_query_survives_an_empty_platform(client):
    admin = await make_admin(client, email="bias-empty-admin@example.com")
    body = (await client.get("/api/v1/admin/bias", headers=auth_headers(admin))).json()
    assert [d["cohorts"] for d in body["dimensions"]] == [[], [], [], []]


def test_analytics_exposes_bias_as_a_live_query():
    assert hasattr(AnalyticsService, "bias")
