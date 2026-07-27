from app.ai.schemas import CVSection, GeneratedCV
from app.services.cvgen import render_markdown
from tests.conftest import auth_headers, create_company, create_specialist


def generated_cv() -> GeneratedCV:
    return GeneratedCV(
        headline="Data architect specialising in Microsoft Fabric",
        summary="I design and migrate cloud data platforms. Most recently I led a 40TB "
        "warehouse migration to Microsoft Fabric.",
        sections=[
            CVSection(
                heading="Core skills",
                bullets=[
                    "Microsoft Fabric — led a 40TB warehouse migration",
                    "Azure — designed the landing zone for the same programme",
                ],
            ),
            CVSection(heading="Certifications", bullets=["DP-600", "AZ-305"]),
        ],
    )


def test_markdown_rendering_is_deterministic_and_complete():
    markdown = render_markdown("Anna de Vries", generated_cv())
    assert markdown.startswith("# Anna de Vries\n")
    assert "**Data architect specialising in Microsoft Fabric**" in markdown
    assert "## Core skills" in markdown
    assert "- Microsoft Fabric — led a 40TB warehouse migration" in markdown
    assert "## Certifications" in markdown
    assert markdown.endswith("\n")
    # rendering twice yields byte-identical output — layout is not model output
    assert markdown == render_markdown("Anna de Vries", generated_cv())


async def test_generated_cv_endpoint(client, fake_chat):
    tokens, _ = await create_specialist(client, email="gencv@example.com")

    fake_chat.responses.append(generated_cv())
    response = await client.post(
        "/api/v1/specialists/me/generated-cv", headers=auth_headers(tokens)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["headline"]
    assert len(body["sections"]) == 2
    assert body["markdown"].startswith("# Test User")

    # the writer received the evidence-bearing skill graph, and the name —
    # it is the specialist's own document — but never the rate
    prompt = fake_chat.calls[-1]["user"]
    assert '"name": "Test User"' in prompt
    assert "evidence" in prompt
    assert "hourly_rate" not in prompt
    assert "110" not in prompt


async def test_generated_cv_requires_a_specialist_profile(client):
    company_tokens = await create_company(client, email="gencv-hm@example.com")
    response = await client.post(
        "/api/v1/specialists/me/generated-cv", headers=auth_headers(company_tokens)
    )
    assert response.status_code == 403


async def test_generated_cv_requires_authentication(client):
    assert (await client.post("/api/v1/specialists/me/generated-cv")).status_code == 401


async def test_generation_is_metered_as_its_own_feature(client, fake_chat):
    from tests.test_admin import make_admin

    tokens, _ = await create_specialist(client, email="gencv-meter@example.com")
    fake_chat.responses.append(generated_cv())
    await client.post("/api/v1/specialists/me/generated-cv", headers=auth_headers(tokens))

    admin = await make_admin(client, email="gencv-admin@example.com")
    usage = (
        (await client.get("/api/v1/admin/metrics", headers=auth_headers(admin))).json()[
            "ai_calls_by_feature"
        ]
    )
    assert usage.get("cv_generator", 0) >= 1
