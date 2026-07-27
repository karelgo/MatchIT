"""The iOS DTOs must decode real API responses.

CI cannot compile the Swift app, so nothing else would catch a backend field
being renamed, removed, or made nullable underneath a non-optional Swift
property — which is a hard crash in `JSONDecoder`, not a degraded screen.

The precise crash condition is narrow: a non-optional *stored* property whose key
is absent or null. Extra JSON keys are ignored by Codable, and computed properties
are never decoded, so neither is a failure.
"""

import re
from pathlib import Path

import pytest

from tests.conftest import auth_headers, create_company
from tests.test_chat import make_mutual_match
from tests.test_contracts import TERMS, draft_of
from tests.test_enrichment import CV_TEXT, cv_extraction
from tests.test_interviews import assessment_of, plan_of
from tests.test_team import proposal_of as team_proposal_of

MODELS_SWIFT = (
    Path(__file__).resolve().parents[2] / "ios" / "MatchIT" / "Core" / "Models.swift"
)
STRUCT_RE = re.compile(r"struct (\w+): [^{]*\{(.*?)\n\}", re.S)
PROPERTY_RE = re.compile(r"\s*(?:let|var)\s+(\w+)\s*:\s*(.+?)\s*$")


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def parse_swift_structs() -> dict[str, dict[str, str]]:
    """{struct: {snake_case_field: swift_type}} for stored properties only."""
    source = MODELS_SWIFT.read_text()
    structs: dict[str, dict[str, str]] = {}
    for name, body in STRUCT_RE.findall(source):
        fields = {}
        for line in body.splitlines():
            match = PROPERTY_RE.match(line)
            if not match:
                continue
            field, swift_type = match.groups()
            if "{" in swift_type:  # computed property — never decoded
                continue
            if "=" in swift_type:  # has a default; decoding still requires the key
                swift_type = swift_type.split("=")[0].strip()
            fields[_snake(field)] = swift_type.strip()
        structs[name] = fields
    return structs


@pytest.fixture
async def payloads(client, fake_chat) -> dict[str, dict]:
    """One real response payload per Swift DTO."""
    collected: dict[str, dict] = {}

    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email="contract-hm@example.com"
    )
    collected["Match"] = match
    collected["MatchSpecialistView"] = match["specialist"]
    collected["AssignmentBrief"] = match["assignment"]
    collected["AssignmentRequirements"] = match["assignment"]["requirements"]
    collected["RoleRequirement"] = match["assignment"]["requirements"]["roles"][0]
    collected["BudgetRange"] = match["assignment"]["requirements"]["budget"]

    collected["User"] = (
        await client.get("/api/v1/users/me", headers=auth_headers(company_tokens))
    ).json()
    collected["SpecialistProfile"] = (
        await client.get("/api/v1/specialists/me", headers=auth_headers(specialist_tokens))
    ).json()
    collected["Skill"] = collected["SpecialistProfile"]["skills"][0]
    collected["CompanyProfile"] = (
        await client.get("/api/v1/companies/me", headers=auth_headers(company_tokens))
    ).json()

    assignment = (
        await client.get("/api/v1/assignments", headers=auth_headers(company_tokens))
    ).json()[0]
    collected["Assignment"] = assignment
    collected["IntakeMessage"] = assignment["intake_history"][0]

    conversation = (
        await client.get("/api/v1/conversations", headers=auth_headers(company_tokens))
    ).json()[0]
    collected["Conversation"] = conversation
    collected["ChatMessage"] = (
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=auth_headers(company_tokens),
            json={"content": "hello"},
        )
    ).json()

    # interview, driven to completion so the assessment shape is covered too
    fake_chat.responses.append(plan_of())
    interview = (
        await client.post(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
        )
    ).json()
    collected["InterviewQuestion"] = interview["questions"][0]
    for index in range(interview["total_questions"]):
        if index == interview["total_questions"] - 1:
            fake_chat.responses.append(assessment_of(0.8))
        interview = (
            await client.post(
                f"/api/v1/matches/{match['id']}/interview/answer",
                headers=auth_headers(specialist_tokens),
                json={"answer": f"Concrete answer number {index}."},
            )
        ).json()
    collected["Interview"] = interview
    collected["TranscriptEntry"] = interview["transcript"][0]
    # company projection carries the full assessment
    company_interview = (
        await client.get(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
        )
    ).json()
    collected["InterviewAssessment"] = company_interview["assessment"]
    collected["AnswerScore"] = company_interview["assessment"]["per_question"][0]

    # engagement contract, drafted and signed by both parties
    fake_chat.responses.append(draft_of())
    contract = (
        await client.post(
            f"/api/v1/matches/{match['id']}/contract",
            headers=auth_headers(company_tokens),
            json=TERMS,
        )
    ).json()
    await client.post(
        f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(company_tokens)
    )
    contract = (
        await client.post(
            f"/api/v1/matches/{match['id']}/contract/sign", headers=auth_headers(specialist_tokens)
        )
    ).json()
    collected["Contract"] = contract
    collected["ContractDraft"] = contract["draft"]
    collected["ContractClause"] = contract["draft"]["clauses"][0]

    # CV enrichment, so the evidenced-skill shape is covered
    fake_chat.responses.append(cv_extraction())
    collected["EnrichmentResult"] = (
        await client.post(
            "/api/v1/specialists/me/enrich/cv",
            headers=auth_headers(specialist_tokens),
            json={"cv_text": CV_TEXT},
        )
    ).json()

    # team allocation for the same assignment
    fake_chat.responses.append(team_proposal_of())
    team = (
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/team", headers=auth_headers(company_tokens)
        )
    ).json()
    collected["Team"] = team
    collected["TeamProposal"] = team["proposal"]
    collected["TeamSeat"] = team["seats"][0]
    collected["TeamMember"] = team["seats"][0]["members"][0]
    collected["TeamRationale"] = team["proposal"]["rationale"][0]

    # TokenResponse comes straight off a fresh registration
    collected["TokenResponse"] = await create_company(client, email="contract-token@example.com")
    return collected


# Request-only DTOs are never decoded from a response.
REQUEST_ONLY = {"SpecialistProfileDraft"}


async def test_every_swift_dto_decodes_a_real_payload(payloads):
    structs = parse_swift_structs()
    assert len(structs) >= 15, "Swift struct parser found suspiciously few structs"

    uncovered = set(structs) - set(payloads) - REQUEST_ONLY
    assert not uncovered, f"no sample payload for Swift DTOs: {sorted(uncovered)}"

    failures = []
    checked = 0
    for name, fields in structs.items():
        if name in REQUEST_ONLY:
            continue
        payload = payloads[name]
        for field, swift_type in fields.items():
            checked += 1
            optional = swift_type.endswith("?")
            if field not in payload:
                if not optional:
                    failures.append(f"{name}.{field}: key ABSENT (Swift {swift_type})")
            elif payload[field] is None and not optional:
                failures.append(f"{name}.{field}: null but Swift type {swift_type} is not optional")
    assert checked >= 80, f"expected to check many fields, only saw {checked}"
    assert not failures, "iOS decode would crash:\n" + "\n".join(failures)


def test_parser_excludes_computed_properties():
    """Guard the guard: computed properties would show up as phantom failures."""
    structs = parse_swift_structs()
    assert "id" not in structs["Skill"], "computed `var id: String { name }` must be excluded"
    assert "is_company" not in structs["IntakeMessage"]
    assert "name" in structs["Skill"], "stored properties must still be found"
