import uuid
from datetime import date

from app.ai.embeddings import FakeEmbeddingModel
from app.ai.schemas import BudgetRange
from app.models import RemotePreference, SpecialistProfile
from app.services.matching import (
    MatchingEngine,
    availability_score,
    language_score,
    location_score,
    rate_score,
    skill_score,
)
from app.services.vector import InMemoryVectorIndex
from tests.conftest import make_requirements

TODAY = date(2026, 7, 20)


def profile(**overrides) -> SpecialistProfile:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        headline="Azure data architect",
        bio="Cloud data platforms",
        skills=[
            {"name": "microsoft fabric", "level": 9, "years": 3},
            {"name": "azure", "level": 9, "years": 8},
            {"name": "data warehousing", "level": 8, "years": 10},
        ],
        languages=["en", "nl"],
        certifications=[],
        years_experience=10,
        hourly_rate=110.0,
        currency="EUR",
        hours_per_week=40,
        available_from=None,
        remote_preference=RemotePreference.REMOTE,
        country="NL",
        city="Utrecht",
        travel_distance_km=50,
        trust_score=0.0,
        trust_breakdown={},
    )
    defaults.update(overrides)
    return SpecialistProfile(**defaults)


def test_skill_score_full_and_partial_coverage():
    requirements = make_requirements()
    complete = profile(
        skills=[
            {"name": "microsoft fabric", "level": 9, "years": 3},
            {"name": "azure", "level": 9, "years": 8},
            {"name": "data warehousing", "level": 8, "years": 10},
            {"name": "power bi", "level": 7, "years": 4},
        ]
    )
    assert skill_score(requirements, complete) == 1.0

    # all must-haves but missing the nice-to-have: 3 / (3 + 1/3) = 0.9
    must_only = skill_score(requirements, profile())
    assert 0.89 < must_only < 0.91

    partial = profile(skills=[{"name": "azure", "level": 9, "years": 8}])
    score = skill_score(requirements, partial)
    assert 0.0 < score < 0.5  # 1 of 3 must-haves, no nice-to-haves


def test_rate_score_bands():
    requirements = make_requirements(budget=BudgetRange(max_hourly=100, currency="EUR"))
    assert rate_score(requirements, profile(hourly_rate=95.0)) == 1.0
    assert rate_score(requirements, profile(hourly_rate=None)) == 0.5
    over = rate_score(requirements, profile(hourly_rate=125.0))
    assert 0.0 < over < 1.0
    assert rate_score(requirements, profile(hourly_rate=200.0)) == 0.0


def test_availability_score():
    requirements = make_requirements(start_date=date(2026, 8, 1))
    assert availability_score(requirements, profile(available_from=None), TODAY) == 1.0
    late = availability_score(requirements, profile(available_from=date(2026, 8, 15)), TODAY)
    assert 0.0 < late < 1.0
    far = availability_score(requirements, profile(available_from=date(2026, 12, 1)), TODAY)
    assert far == 0.0


def test_location_score_onsite_rules():
    onsite = make_requirements(remote_allowed=False, country="NL")
    assert location_score(onsite, profile(remote_preference=RemotePreference.REMOTE)) == 0.0
    assert location_score(onsite, profile(remote_preference=RemotePreference.HYBRID)) == 0.8
    abroad = profile(remote_preference=RemotePreference.ONSITE, country="DE")
    assert location_score(onsite, abroad) == 0.0
    assert location_score(make_requirements(), profile()) == 1.0


def test_language_score():
    requirements = make_requirements(languages=["en", "nl"])
    assert language_score(requirements, profile(languages=["en", "nl"])) == 1.0
    assert language_score(requirements, profile(languages=["en"])) == 0.5
    assert language_score(make_requirements(languages=[]), profile()) == 1.0


async def test_engine_ranks_matching_specialist_first():
    engine = MatchingEngine(FakeEmbeddingModel(), InMemoryVectorIndex())
    fabric_architect = profile()
    frontend_dev = profile(
        headline="React frontend developer",
        bio="Design systems and web apps",
        skills=[{"name": "react", "level": 9, "years": 6}],
        hourly_rate=85.0,
    )
    await engine.index_specialist(fabric_architect)
    await engine.index_specialist(frontend_dev)

    ranked = await engine.rank(
        make_requirements(), [frontend_dev, fabric_architect], today=TODAY
    )

    assert ranked[0].profile.id == fabric_architect.id
    assert ranked[0].score > ranked[1].score
    assert set(ranked[0].breakdown) == {
        "skills",
        "semantic",
        "rate",
        "availability",
        "location",
        "language",
    }
    assert all(0.0 <= v <= 1.0 for v in ranked[0].breakdown.values())
    assert ranked[0].breakdown["semantic"] > ranked[1].breakdown["semantic"]
