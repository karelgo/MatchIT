from app.ai.llm import FakeChatModel
from app.ai.schemas import CVExtraction, EvidencedSkill, GitHubExtraction, SkillSource
from app.services.enrichment import EnrichmentService, merge_skills, summarise_repositories
from app.services.github import FakeGitHubClient, Repository
from tests.conftest import auth_headers, create_specialist, register

CV_TEXT = (
    "Anna de Vries — Data Architect\n"
    "2019-2026 Acme BV: led the migration of a 40TB on-prem warehouse to Microsoft "
    "Fabric, designing the medallion architecture and the Azure landing zone. "
    "2015-2019 Contoso: built ETL pipelines in Python and SQL Server. "
    "Certifications: DP-600, AZ-305. Languages: Dutch, English."
) * 2


def cv_extraction() -> CVExtraction:
    return CVExtraction(
        headline="Data architect specialising in Microsoft Fabric",
        summary=(
            "Fifteen years building cloud data platforms, "
            "most recently a 40TB Fabric migration."
        ),
        years_experience=11,
        skills=[
            EvidencedSkill(
                name="microsoft fabric",
                level=9,
                years=3,
                evidence="Led a 40TB warehouse migration to Fabric at Acme BV",
            ),
            EvidencedSkill(
                name="azure", level=8, years=7, evidence="Designed the Azure landing zone"
            ),
        ],
        certifications=["DP-600", "AZ-305"],
        languages=["nl", "en"],
    )


def github_extraction() -> GitHubExtraction:
    return GitHubExtraction(
        summary="Sustained original work on Fabric tooling in Python.",
        skills=[
            EvidencedSkill(
                name="python",
                level=8,
                years=5,
                evidence="fabric-migrator: 4.2MB of original Python, 120 stars",
            )
        ],
    )


# ---- merge semantics ----


def test_evidence_replaces_self_reported():
    existing = [{"name": "azure", "level": 3, "years": 1}]
    merged = merge_skills(existing, cv_extraction().skills, SkillSource.CV)
    azure = next(s for s in merged if s["name"] == "azure")
    assert azure["level"] == 8
    assert azure["source"] == "cv"
    assert azure["evidence"]


def test_weaker_source_never_overwrites_a_stronger_one():
    """Re-reading a CV must not downgrade an interview-verified skill."""
    existing = [
        {
            "name": "azure",
            "level": 10,
            "years": 9,
            "source": SkillSource.INTERVIEW.value,
            "evidence": "Defended the design in interview",
        }
    ]
    merged = merge_skills(existing, cv_extraction().skills, SkillSource.CV)
    azure = next(s for s in merged if s["name"] == "azure")
    assert azure["level"] == 10
    assert azure["source"] == SkillSource.INTERVIEW.value


def test_merge_never_deletes_existing_skills():
    existing = [{"name": "kubernetes", "level": 7, "years": 4}]
    merged = merge_skills(existing, cv_extraction().skills, SkillSource.CV)
    assert {s["name"] for s in merged} == {"kubernetes", "microsoft fabric", "azure"}
    kubernetes = next(s for s in merged if s["name"] == "kubernetes")
    assert kubernetes["source"] == "self_reported", "untouched skills keep their provenance"


def test_merge_keeps_the_longer_experience():
    existing = [{"name": "azure", "level": 5, "years": 12}]
    merged = merge_skills(existing, cv_extraction().skills, SkillSource.CV)
    azure = next(s for s in merged if s["name"] == "azure")
    assert azure["years"] == 12, "a CV extract must not shorten known experience"


def test_names_are_canonicalised():
    merged = merge_skills(
        [{"name": "  Azure  ", "level": 4, "years": 1}], cv_extraction().skills, SkillSource.CV
    )
    assert all(s["name"] == s["name"].strip().lower() for s in merged)
    assert len([s for s in merged if s["name"] == "azure"]) == 1


# ---- repository projection ----


def test_forks_and_empty_repositories_are_dropped():
    repositories = [
        Repository("real", "d", "Python", 10, False, 900, "2026-01-01T00:00:00Z", []),
        Repository("forked", None, "Go", 0, True, 500, None, []),
        Repository("empty", None, None, 0, False, 0, None, []),
    ]
    payload = summarise_repositories(repositories)
    assert payload["repository_count"] == 3
    assert payload["original_repository_count"] == 1
    assert [r["name"] for r in payload["repositories"]] == ["real"]


# ---- service ----


async def test_github_service_reports_repository_count():
    chat = FakeChatModel(responses=[github_extraction()])
    client = FakeGitHubClient(
        {"dev": [Repository("x", "d", "Python", 3, False, 800, None, [])]}
    )
    service = EnrichmentService(chat, client)
    extraction, count = await service.from_github("dev")
    assert count == 1
    assert extraction.skills[0].name == "python"
    assert "repositories" in chat.calls[0]["user"]


# ---- API ----


async def test_cv_enrichment_updates_the_profile(client, fake_chat):
    tokens, _ = await create_specialist(client, email="cv@example.com")

    fake_chat.responses.append(cv_extraction())
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv",
        headers=auth_headers(tokens),
        json={"cv_text": CV_TEXT},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "cv"
    assert body["evidence_count"] >= 2
    assert body["summary"]

    profile = body["profile"]
    assert profile["headline"] == "Data architect specialising in Microsoft Fabric"
    assert "DP-600" in profile["certifications"]
    assert set(profile["languages"]) >= {"nl", "en"}

    evidenced = {s["name"]: s for s in profile["skills"]}
    assert evidenced["microsoft fabric"]["source"] == "cv"
    assert evidenced["microsoft fabric"]["evidence"]
    # the seeded self-reported skill survives with its provenance intact
    assert evidenced["data warehousing"]["source"] == "self_reported"

    # the CV text reached the extractor
    assert "40TB" in fake_chat.calls[-1]["user"]


async def test_cv_enrichment_never_shortens_known_experience(client, fake_chat):
    tokens, profile = await create_specialist(client, email="cv2@example.com")
    assert profile["years_experience"] == 10

    fake_chat.responses.append(cv_extraction().model_copy(update={"years_experience": 2}))
    body = (
        await client.post(
            "/api/v1/specialists/me/enrich/cv",
            headers=auth_headers(tokens),
            json={"cv_text": CV_TEXT},
        )
    ).json()
    assert body["profile"]["years_experience"] == 10


async def test_github_enrichment_records_the_profile_url(client, fake_chat):
    tokens, _ = await create_specialist(client, email="gh@example.com")

    fake_chat.responses.append(github_extraction())
    response = await client.post(
        "/api/v1/specialists/me/enrich/github",
        headers=auth_headers(tokens),
        json={"username": "octospecialist"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "github"
    assert body["profile"]["github_url"] == "https://github.com/octospecialist"
    python = next(s for s in body["profile"]["skills"] if s["name"] == "python")
    assert python["source"] == "github"
    assert "fabric-migrator" in python["evidence"]

    # the fork was excluded before the model ever saw it
    prompt = fake_chat.calls[-1]["user"]
    assert "fabric-migrator" in prompt
    assert "awesome-list-fork" not in prompt


async def test_github_enrichment_rejects_unknown_user(client):
    tokens, _ = await create_specialist(client, email="gh404@example.com")
    response = await client.post(
        "/api/v1/specialists/me/enrich/github",
        headers=auth_headers(tokens),
        json={"username": "nobody"},
    )
    assert response.status_code == 502


async def test_github_enrichment_rejects_a_user_with_only_forks(client, fake_chat):
    """And does so without paying for a model call that can only say "nothing here"."""
    tokens, _ = await create_specialist(client, email="ghfork@example.com")
    calls_before = len(fake_chat.calls)
    response = await client.post(
        "/api/v1/specialists/me/enrich/github",
        headers=auth_headers(tokens),
        json={"username": "emptyuser"},
    )
    assert response.status_code == 422
    assert len(fake_chat.calls) == calls_before, "no model call should be made"


async def test_enrichment_requires_a_specialist_profile(client):
    tokens = await register(client, email="nohost@example.com", role="hiring_manager")
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv",
        headers=auth_headers(tokens),
        json={"cv_text": CV_TEXT},
    )
    assert response.status_code == 403


async def test_short_cv_is_rejected(client):
    tokens, _ = await create_specialist(client, email="shortcv@example.com")
    response = await client.post(
        "/api/v1/specialists/me/enrich/cv",
        headers=auth_headers(tokens),
        json={"cv_text": "too short"},
    )
    assert response.status_code == 422
