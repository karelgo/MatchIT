"""The registry of AI systems MatchIT operates, and the model cards generated from it.

Recruitment AI is high-risk under the EU AI Act: Article 11 requires technical
documentation of each system, and Article 50 requires telling the people subject to
one that they are dealing with one. Documentation written by hand is wrong by the
second release, so nothing here is maintained twice: every entry points at the
*actual* prompt constant or parameter table the feature runs on, and its card
carries a fingerprint of that text. Edit a prompt or a ranking weight and the
fingerprint in the generated documentation changes in the same commit.

The registry deliberately includes the systems that are not language models. The
ranking function decides who a company ever sees, which makes it the highest-impact
automated decision in the product; leaving it out because it has no prompt would
document the easy half.
"""

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel

from app.ai import prompts
from app.ai.schemas import (
    AssignmentRequirements,
    ContractDraft,
    CVExtraction,
    GeneratedCV,
    GitHubExtraction,
    InterviewAssessment,
    InterviewPlan,
    TeamProposal,
)
from app.services.matching import NICE_TO_HAVE_WEIGHT, WEIGHTS


@dataclass(frozen=True)
class AISystem:
    """One documented automated system.

    `definition` is the exact text the system runs on — a system prompt, or a
    rendering of the parameters for the ones that have no prompt. It is the thing
    fingerprinted, so the card can never claim a behaviour the code no longer has.
    """

    key: str
    name: str
    kind: str  # llm | deterministic | embedding
    purpose: str
    definition: str
    inputs: tuple[str, ...]
    used_for: str
    human_oversight: str
    limitations: tuple[str, ...]
    personal_data: tuple[str, ...]
    # Usage-metering label; several systems share one (the two interview stages
    # are both billed as "interview"). None for systems that call no model.
    feature: str | None = None
    output_schema: type[BaseModel] | None = None

    @property
    def fingerprint(self) -> str:
        """Stable identifier for this exact definition text."""
        return hashlib.sha256(self.definition.encode("utf-8")).hexdigest()[:16]

    def card(self, *, include_definition: bool = False) -> dict:
        card = {
            "key": self.key,
            "name": self.name,
            "kind": self.kind,
            "purpose": self.purpose,
            "definition_fingerprint": self.fingerprint,
            "inputs": list(self.inputs),
            "used_for": self.used_for,
            "human_oversight": self.human_oversight,
            "limitations": list(self.limitations),
            "personal_data": list(self.personal_data),
            "metering_label": self.feature,
            "output_schema": (
                self.output_schema.__name__ if self.output_schema is not None else None
            ),
        }
        if include_definition:
            card["definition"] = self.definition
        return card


RANKING_COMPONENT_DOC = {
    "skills": "share of the assignment's must-have skills the profile claims "
    "(nice-to-haves count fractionally)",
    "semantic": "cosine similarity between the assignment text and the profile text",
    "rate": "1.0 within budget, decaying linearly to 0 at 50% over budget",
    "availability": "1.0 if available by the start date, -25% per week later",
    "location": "on-site assignments discount remote-only or out-of-country profiles",
    "language": "share of the required working languages the profile speaks",
}


def _ranking_definition() -> str:
    """Canonical rendering of the ranking function's parameters.

    Rendered rather than restated so that changing a weight changes the published
    fingerprint — the documentation cannot silently describe last month's model.
    """
    lines = [
        "MatchIT ranking function",
        "",
        "score = sum(weight[c] * component[c]) for c in components",
        "Every component is clamped to [0, 1]; the weighted breakdown is persisted",
        "with the match and shown to both parties.",
        "",
    ]
    lines += [
        f"{weight:.2f}  {name}: {RANKING_COMPONENT_DOC[name]}"
        for name, weight in WEIGHTS.items()
    ]
    lines += [
        "",
        f"A nice-to-have skill counts {NICE_TO_HAVE_WEIGHT:.4f} of a must-have skill.",
        "Candidate recall is unfiltered: every specialist profile is scored, and the",
        "vector index supplies the semantic component rather than a shortlist.",
    ]
    return "\n".join(lines)


_NO_PROTECTED_ATTRIBUTES = (
    "Age, gender, nationality, ethnicity, health and religion are never collected, "
    "inferred or used. The CV reader is instructed to discard them even when the "
    "source document states them."
)

_HUMAN_DECIDES = (
    "Advisory only. The system produces no outcome by itself: a human on each side "
    "accepts or rejects, and both signatures are required before any engagement exists."
)


SYSTEMS: tuple[AISystem, ...] = (
    AISystem(
        key="intake",
        name="Assignment intake analyst",
        kind="llm",
        feature="intake",
        purpose=(
            "Turn a company's free-text description of a business problem into a "
            "structured assignment: roles, seniority, must-have and nice-to-have "
            "skills, languages, location, timeline and budget."
        ),
        definition=prompts.INTAKE_SYSTEM_PROMPT,
        output_schema=AssignmentRequirements,
        inputs=(
            "the company's problem statement",
            "the full intake dialogue, including the company's answers to clarifying "
            "questions",
        ),
        used_for="the requirements the ranking function scores candidates against",
        human_oversight=(
            "The company reviews and refines the extracted assignment before any "
            "matching runs, and every field remains editable."
        ),
        limitations=(
            "Budget and duration are estimated from European market rates when the "
            "company states neither; estimates are flagged as such in the API and in "
            "the app, and are never presented as stated terms.",
            "Skill names are normalised to canonical lower-case forms, so an unusual "
            "in-house technology name may be normalised to a near neighbour.",
        ),
        personal_data=(
            "None about specialists. Company-side input may contain the author's own "
            "description of their team.",
        ),
    ),
    AISystem(
        key="ranking",
        name="Specialist ranking function",
        kind="deterministic",
        feature=None,
        purpose=(
            "Rank specialist profiles against a structured assignment and produce the "
            "score breakdown that is shown to both parties."
        ),
        definition=_ranking_definition(),
        output_schema=None,
        inputs=(
            "the structured assignment",
            "the specialist's skills, rate, availability, location and languages",
            "the semantic similarity of the two texts",
        ),
        used_for="the order in which a company sees candidates, and the opportunity inbox",
        human_oversight=_HUMAN_DECIDES,
        limitations=(
            "Skill matching is by canonical name, so a skill the specialist has but "
            "has not recorded scores zero. The interview exists to find exactly this.",
            "A profile that has never been enriched from a CV or repository is scored "
            "on self-reported claims, which the score breakdown makes visible.",
            "No candidate is filtered out before scoring, so a low rank is a low score "
            "and not an exclusion.",
        ),
        personal_data=(
            "Professional attributes only: skills, years of experience, rate, "
            "availability, country, city, languages.",
            _NO_PROTECTED_ATTRIBUTES,
        ),
    ),
    AISystem(
        key="embedding",
        name="Semantic profile and assignment embedding",
        kind="embedding",
        feature=None,
        purpose=(
            "Represent assignment text and profile text as vectors so that relevant "
            "experience described in different words still matches."
        ),
        definition=(
            prompts.PROFILE_EMBEDDING_TEMPLATE + "\n---\n" + prompts.ASSIGNMENT_EMBEDDING_TEMPLATE
        ),
        output_schema=None,
        inputs=("the profile headline, bio, skills, certifications and languages",),
        used_for="the `semantic` component of the ranking function, weighted at "
        f"{WEIGHTS['semantic']:.0%}",
        human_oversight=_HUMAN_DECIDES,
        limitations=(
            "Similarity reflects how the two texts are written. A terse profile "
            "scores lower on this component than a fluent one describing the same work.",
            "The component is capped at the weight above precisely because writing "
            "quality must not dominate evidence of skill.",
        ),
        personal_data=("The free-text profile the specialist wrote about themselves.",),
    ),
    AISystem(
        key="interview_plan",
        name="Screening interview planner",
        kind="llm",
        feature="interview",
        purpose=(
            "Design a short written interview aimed at the must-have skills the "
            "profile does not already evidence."
        ),
        definition=prompts.INTERVIEW_PLAN_SYSTEM_PROMPT,
        output_schema=InterviewPlan,
        inputs=(
            "the structured assignment",
            "a projection of the profile that excludes name, contact details and rate",
            "the must-have skills the profile does not claim",
        ),
        used_for="the questions asked, each published with the rationale for asking it",
        human_oversight=(
            "Every question and its rationale are visible to both parties before and "
            "after the interview. The specialist may decline to take it."
        ),
        limitations=(
            "The plan is built from the profile as recorded; a profile that "
            "understates experience yields questions that feel basic.",
            "The prompt forbids questions about age, health, family, nationality or "
            "religion — anything that cannot lawfully inform an EU hiring decision.",
        ),
        personal_data=(
            "Professional profile content only. The planner is deliberately not told "
            "who the specialist is or what they cost.",
        ),
    ),
    AISystem(
        key="interview_assessment",
        name="Screening interview assessor",
        kind="llm",
        feature="interview",
        purpose="Score written interview answers against the assignment's requirements.",
        definition=prompts.INTERVIEW_ASSESSMENT_SYSTEM_PROMPT,
        output_schema=InterviewAssessment,
        inputs=(
            "the structured assignment",
            "the profile projection",
            "the transcript of questions and answers",
        ),
        used_for=(
            "a hiring-manager recommendation, feedback for the specialist, and one "
            "input to the trust score"
        ),
        human_oversight=(
            "The recommendation is advice. The hiring manager decides, and the "
            "per-question reasoning is published so the decision can be argued with."
        ),
        limitations=(
            "Answers may be spoken and transcribed. Only content is scored: "
            "delivery, accent, fluency, speed and transcription artefacts are "
            "excluded by the prompt, and no audio or video is ever analysed.",
            "The score reflects what the transcript evidences, which is a floor on "
            "ability and never a ceiling.",
            "Emotion, personality and affect are not inferred. Inferring emotion in a "
            "workplace context is prohibited by the EU AI Act and MatchIT runs no such "
            "system.",
        ),
        personal_data=(
            "The answers the specialist chose to write or say.",
            _NO_PROTECTED_ATTRIBUTES,
        ),
    ),
    AISystem(
        key="cv_extraction",
        name="CV skill extractor",
        kind="llm",
        feature="enrichment",
        purpose=(
            "Read an uploaded CV into the skill graph, with every skill citing the "
            "role or project in the document that supports it."
        ),
        definition=prompts.CV_EXTRACTION_SYSTEM_PROMPT,
        output_schema=CVExtraction,
        inputs=("the text of a CV the specialist uploaded themselves",),
        used_for="the specialist's own profile: skills, levels, certifications, languages",
        human_oversight=(
            "The specialist uploads their own CV, sees every extracted skill with its "
            "evidence, and can edit or remove any of it."
        ),
        limitations=(
            "Enrichment never deletes and never downgrades: a skill already verified "
            "by an interview outranks the same skill read from a CV.",
            "A scanned CV with no text layer is rejected rather than guessed at.",
        ),
        personal_data=(
            "Whatever the specialist's own CV contains.",
            _NO_PROTECTED_ATTRIBUTES,
        ),
    ),
    AISystem(
        key="github_extraction",
        name="Public repository analyser",
        kind="llm",
        feature="enrichment",
        purpose="Infer demonstrated skills from a specialist's public repositories.",
        definition=prompts.GITHUB_EXTRACTION_SYSTEM_PROMPT,
        output_schema=GitHubExtraction,
        inputs=(
            "public repository metadata for a username the specialist supplied: name, "
            "description, language, stars, size and last push",
        ),
        used_for="skills on the specialist's own profile, each citing a repository",
        human_oversight=(
            "Opt-in per specialist, and the resulting skills are visible and editable."
        ),
        limitations=(
            "Forks and empty repositories are discarded before the model is called, so "
            "an account with only forks costs nothing and adds nothing.",
            "Absence of public code is never evidence against a skill.",
        ),
        personal_data=("Public repository metadata for a username the specialist gave us.",),
    ),
    AISystem(
        key="cv_generator",
        name="CV writer",
        kind="llm",
        feature="cv_generator",
        purpose="Write a CV for a specialist from their evidence-backed profile.",
        definition=prompts.CV_GENERATOR_SYSTEM_PROMPT,
        output_schema=GeneratedCV,
        inputs=("the specialist's own profile, including each skill's evidence",),
        used_for="a document the specialist may share; it feeds no ranking",
        human_oversight="Generated on request by the specialist, for the specialist.",
        limitations=(
            "The prompt forbids inventing employers, dates, projects or outcomes, so a "
            "thin profile yields a short CV. That is the intended behaviour.",
        ),
        personal_data=("The specialist's own profile.",),
    ),
    AISystem(
        key="team_builder",
        name="Team composition reviewer",
        kind="llm",
        feature="team_builder",
        purpose=(
            "Explain and critique a seat-by-seat team allocation for a multi-role "
            "assignment."
        ),
        definition=prompts.TEAM_BUILDER_SYSTEM_PROMPT,
        output_schema=TeamProposal,
        inputs=("the assignment's roles and seats", "the allocation and its scores"),
        used_for="a written rationale, strengths and gaps shown to the company",
        human_oversight=(
            "The allocation itself is deterministic; the model explains it and does "
            "not reorder it. A seat with no viable candidate stays visibly open."
        ),
        limitations=(
            "Seats are filled only above a minimum score, so an open seat means no "
            "suitable candidate was found rather than none existing.",
        ),
        personal_data=("Specialist headlines and skills for the allocated candidates.",),
    ),
    AISystem(
        key="contract",
        name="Engagement contract drafter",
        kind="llm",
        feature="contract",
        purpose=(
            "Draft an EU engagement contract from the assignment and the commercial "
            "terms both parties agreed."
        ),
        definition=prompts.CONTRACT_SYSTEM_PROMPT,
        output_schema=ContractDraft,
        inputs=("the structured assignment", "the agreed terms", "both parties' countries"),
        used_for="a draft both parties read and sign in-app",
        human_oversight=(
            "Both parties read the draft and sign it; nothing takes effect without "
            "both signatures. The draft is not legal advice."
        ),
        limitations=(
            "The model never invents a rate, date, duration or notice period: anything "
            "missing goes to `open_points` for a lawyer instead of being guessed.",
        ),
        personal_data=("The parties' names, countries and agreed commercial terms.",),
    ),
)

SYSTEMS_BY_KEY: dict[str, AISystem] = {system.key: system for system in SYSTEMS}


def cards(*, include_definitions: bool = False) -> list[dict]:
    return [system.card(include_definition=include_definitions) for system in SYSTEMS]


TRANSPARENCY_STATEMENT = (
    "MatchIT uses automated systems throughout hiring and tells you so, which is what "
    "Article 50 of the EU AI Act requires. Recruitment AI is high-risk under that Act, "
    "so each system below is documented with its purpose, its inputs, its limitations "
    "and the human oversight applied to it. No system here decides anything on its own: "
    "a person on each side accepts or rejects, and an engagement exists only once both "
    "have signed."
)


def model_card_markdown() -> str:
    """Render the registry as documentation.

    Generated, never hand-edited: `scripts/generate_model_cards.py` writes it to
    `docs/ai-systems.md` and a test fails if the committed file has drifted.
    """
    lines = [
        "# MatchIT — AI systems",
        "",
        "<!-- Generated from app/services/aisystems.py by scripts/generate_model_cards.py.",
        "     Do not edit by hand: run the script. -->",
        "",
        TRANSPARENCY_STATEMENT,
        "",
        "Each system carries a **definition fingerprint**: the first 16 hex characters of "
        "the SHA-256 of the exact prompt or parameter table it runs on. A transparency "
        "report cites the fingerprints that were in force for that hire, so a card can "
        "be matched to the decision it actually governed.",
        "",
        "| System | Kind | Fingerprint | Output |",
        "| --- | --- | --- | --- |",
    ]
    for system in SYSTEMS:
        schema = system.output_schema.__name__ if system.output_schema else "—"
        lines.append(
            f"| {system.name} | {system.kind} | `{system.fingerprint}` | {schema} |"
        )
    lines.append("")

    for system in SYSTEMS:
        lines += [
            f"## {system.name}",
            "",
            f"- **Key:** `{system.key}`",
            f"- **Kind:** {system.kind}",
            f"- **Definition fingerprint:** `{system.fingerprint}`",
            "- **Usage-metering label:** "
            + (f"`{system.feature}`" if system.feature else "not model-backed"),
            "- **Output contract:** "
            + (f"`{system.output_schema.__name__}`" if system.output_schema else "not applicable"),
            "",
            f"**Purpose.** {system.purpose}",
            "",
            "**Inputs.**",
            "",
        ]
        lines += [f"- {item}" for item in system.inputs]
        lines += [
            "",
            f"**What the output is used for.** {system.used_for}",
            "",
            f"**Human oversight.** {system.human_oversight}",
            "",
            "**Limitations and known failure modes.**",
            "",
        ]
        lines += [f"- {item}" for item in system.limitations]
        lines += ["", "**Personal data.**", ""]
        lines += [f"- {item}" for item in system.personal_data]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
