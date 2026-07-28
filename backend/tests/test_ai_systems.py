"""The AI system registry, and the documentation generated from it.

These are structural guards. The ordinary suite cannot see a prompt that was added
without being documented, or a doc that quietly describes last month's model — both
are exactly the failures that make published AI documentation worthless.
"""

import subprocess
import sys
from pathlib import Path

from app.ai import prompts
from app.services import aisystems
from app.services.aisystems import SYSTEMS, SYSTEMS_BY_KEY, model_card_markdown
from tests.conftest import auth_headers, create_specialist

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = BACKEND_ROOT.parent / "docs" / "ai-systems.md"


def test_every_system_prompt_is_documented():
    """A new AI feature must not be able to ship undocumented."""
    documented = {system.definition for system in SYSTEMS}
    undocumented = [
        name
        for name in dir(prompts)
        if name.endswith("_SYSTEM_PROMPT") and getattr(prompts, name) not in documented
    ]
    assert not undocumented, (
        "these prompts have no entry in app/services/aisystems.py: "
        f"{sorted(undocumented)}"
    )


def test_the_prompt_scan_actually_finds_prompts():
    """Guard the guard: a selector matching nothing would pass above."""
    names = [name for name in dir(prompts) if name.endswith("_SYSTEM_PROMPT")]
    assert len(names) >= 7, names


def test_fingerprints_are_unique_and_track_the_definition():
    fingerprints = [system.fingerprint for system in SYSTEMS]
    assert len(set(fingerprints)) == len(fingerprints)
    assert all(len(value) == 16 for value in fingerprints)

    original = SYSTEMS_BY_KEY["intake"]
    edited = aisystems.AISystem(**{**vars(original), "definition": original.definition + " "})
    assert edited.fingerprint != original.fingerprint


def test_the_ranking_fingerprint_moves_when_a_weight_moves(monkeypatch):
    """Weights are model parameters; documentation that misses a change is a lie."""
    before = aisystems._ranking_definition()
    monkeypatch.setitem(aisystems.WEIGHTS, "skills", 0.55)
    after = aisystems._ranking_definition()
    assert before != after
    assert "0.55" in after


def test_the_non_model_systems_are_documented_too():
    """The ranking function decides who is ever seen; omitting it documents half."""
    kinds = {system.key: system.kind for system in SYSTEMS}
    assert kinds["ranking"] == "deterministic"
    assert kinds["embedding"] == "embedding"
    assert SYSTEMS_BY_KEY["ranking"].feature is None


def test_every_card_states_oversight_limitations_and_personal_data():
    for system in SYSTEMS:
        assert system.purpose and system.used_for and system.human_oversight
        assert system.inputs, f"{system.key} lists no inputs"
        assert system.limitations, f"{system.key} claims no limitations"
        assert system.personal_data, f"{system.key} does not say what it processes"


def test_the_assessor_card_rules_out_emotion_inference():
    """Prohibited under the AI Act since February 2025; the card must say so."""
    limitations = " ".join(SYSTEMS_BY_KEY["interview_assessment"].limitations).lower()
    assert "emotion" in limitations
    assert "prohibited" in limitations
    assert "no audio or video" in limitations


def test_the_assessment_prompt_forbids_scoring_delivery():
    """Voice answers only stay safe while the prompt says content only."""
    prompt = prompts.INTERVIEW_ASSESSMENT_SYSTEM_PROMPT.lower()
    assert "spoken and transcribed" in prompt
    assert "must not lower a score" in prompt
    assert "never infer confidence, personality, emotion or fluency" in prompt


def test_cards_omit_the_prompt_text_unless_asked():
    """Prompts are shipped in the repository, not leaked through a public card."""
    assert "definition" not in aisystems.cards()[0]
    assert "definition" in aisystems.cards(include_definitions=True)[0]


def test_committed_documentation_matches_the_registry():
    """`docs/ai-systems.md` is generated; drift means the published doc is wrong."""
    assert DOC_PATH.exists(), "run scripts/generate_model_cards.py"
    assert DOC_PATH.read_text(encoding="utf-8") == model_card_markdown(), (
        "docs/ai-systems.md is stale — run: python scripts/generate_model_cards.py"
    )


def test_the_generator_check_mode_agrees():
    result = subprocess.run(
        [sys.executable, "scripts/generate_model_cards.py", "--check"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_the_api_publishes_the_same_cards(client):
    tokens, _ = await create_specialist(client, email="cards@example.com")
    body = (await client.get("/api/v1/ai/systems", headers=auth_headers(tokens))).json()

    assert len(body["systems"]) == len(SYSTEMS)
    assert {system["key"] for system in body["systems"]} == set(SYSTEMS_BY_KEY)
    assert "Article 50" in body["statement"]
    assert body["markdown"] == model_card_markdown()
    for card in body["systems"]:
        assert "definition" not in card


async def test_the_cards_need_a_session(client):
    response = await client.get("/api/v1/ai/systems")
    assert response.status_code == 401
