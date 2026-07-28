"""AI transparency reports: one signed artifact per hiring decision.

The EU AI Act puts recruitment AI in the high-risk category, which means the people
subject to it are entitled to know how a decision about them was reached, and the
organisation deploying it has to be able to show its work. Both obligations are
satisfied by the same document, so MatchIT produces one: what the ranking function
scored and why, what the interview asked and why it asked it, what each side decided
and when, and which AI systems — at which exact prompt fingerprint — were involved.

Two decisions worth stating plainly:

*Both parties receive the identical document.* The interview API projects its
assessment per viewer, because a candidate mid-screening should not be reading
"recommendation: no" as a live UI element. A transparency report is not that: it is
issued only once a decision has been made, and a report that concealed the
conclusion the AI reached about someone would not be a transparency report. So the
projection does not apply here, and the artifact is the same for everyone — which is
also what makes a shared signature meaningful.

*The signature is an HMAC, not a public-key signature.* The claim it supports is
"MatchIT issued this exact document and it has not been altered since", verifiable
by handing the document back to `/transparency-reports/verify`. A third party
holding only the document cannot verify it unaided; that would need a published key
and a key-rotation story, which is a deliberate later step, not a silently missing
one.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import AssignmentRequirements, InterviewPlan
from app.models import Contract, Decision, Interview, InterviewStatus, Match
from app.services.aisystems import RANKING_COMPONENT_DOC, SYSTEMS_BY_KEY
from app.services.matching import WEIGHTS

REPORT_VERSION = "1"
SIGNATURE_ALGORITHM = "HMAC-SHA256"

# Domain separation: the report key is derived from the application secret rather
# than being the application secret, so a transparency signature can never be
# confused with — or used to forge — anything else signed with the same secret.
_KEY_LABEL = b"matchit/transparency-report/v1"

_STATEMENT = (
    "This report describes how MatchIT's automated systems handled one candidacy: "
    "what was scored, what was asked, what the systems concluded, and which human "
    "made which decision. It is issued to both parties in identical form."
)

_HUMAN_OVERSIGHT = (
    "No automated system in MatchIT decides anything. Ranking orders candidates for a "
    "human to review; the interview assessment is advice to a human; acceptance and "
    "rejection are recorded human acts, timestamped below; and an engagement exists "
    "only once both parties have signed. Nothing in this report was decided by a "
    "system on its own, which is why every decision below names the party that made it."
)

_RIGHTS = (
    "You may request all data MatchIT holds about you (GDPR Art. 15/20) from your "
    "account at any time.",
    "You may contest any decision recorded here and ask for it to be reviewed by a "
    "person, using the score components and interview reasoning printed above as the "
    "basis of your argument.",
    "You may request erasure (GDPR Art. 17). Erasure is refused only while a signed "
    "contract is in force, because a live obligation binds both sides.",
    "MatchIT does not analyse audio, video, facial expression, affect or emotion. "
    "Inferring emotion in a workplace context is prohibited under the EU AI Act, and "
    "no such system exists in this product.",
)


class ReportNotAvailable(Exception):
    """The report is not issuable yet — no decision has been made to report on."""


def canonical_json(payload: dict) -> str:
    """The exact byte sequence a signature covers.

    Sorted keys and no insignificant whitespace, so a document that survives a
    round trip through any JSON library still verifies.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def rank_within_assignment(db: AsyncSession, match: Match) -> tuple[int, int]:
    """Where this candidate ranked, and how large the field was.

    A rank is only meaningful next to the size of the field: "3rd of 4" and
    "3rd of 400" are not the same statement, so both always travel together.
    """
    considered = int(
        await db.scalar(
            select(func.count())
            .select_from(Match)
            .where(Match.assignment_id == match.assignment_id)
        )
        or 0
    )
    ahead = int(
        await db.scalar(
            select(func.count())
            .select_from(Match)
            .where(Match.assignment_id == match.assignment_id, Match.score > match.score)
        )
        or 0
    )
    return ahead + 1, considered


def specialist_reference(specialist_id: uuid.UUID) -> str:
    """A stable pseudonym for the specialist.

    The report is a document that gets forwarded — to a client, an auditor, a tax
    inspector — so it identifies the candidacy without carrying a name into places
    the candidate never agreed to be named.
    """
    digest = hashlib.sha256(f"matchit-specialist:{specialist_id}".encode()).hexdigest()
    return f"SP-{digest[:10].upper()}"


class TransparencyService:
    def __init__(self, secret: str):
        self._key = hmac.new(secret.encode("utf-8"), _KEY_LABEL, hashlib.sha256).digest()

    # ---- signing ----

    def sign(self, body: dict) -> str:
        return hmac.new(
            self._key, canonical_json(body).encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def verify(self, document: dict) -> bool:
        """True when `document` is exactly as MatchIT issued it."""
        signature = document.get("signature")
        if not isinstance(signature, dict):
            return False
        value = signature.get("value")
        if not isinstance(value, str):
            return False
        body = {key: item for key, item in document.items() if key != "signature"}
        return hmac.compare_digest(value, self.sign(body))

    # ---- building ----

    async def build(self, db: AsyncSession, match: Match) -> dict:
        """Assemble and sign the report for one match.

        Raises `ReportNotAvailable` while the company has not decided: until then
        there is no decision to be transparent about, and issuing a document
        mid-screening would put the AI's conclusion in front of the candidate
        before a person has weighed it.
        """
        if match.company_decision == Decision.PENDING:
            raise ReportNotAvailable(
                "a transparency report is issued once the company has decided on this match"
            )

        requirements = AssignmentRequirements.model_validate(match.assignment.requirements)
        interview = await db.scalar(select(Interview).where(Interview.match_id == match.id))
        contract = await db.scalar(select(Contract).where(Contract.match_id == match.id))
        rank, considered = await rank_within_assignment(db, match)

        systems_used = ["ranking", "embedding", "intake"]
        if interview is not None:
            systems_used.append("interview_plan")
            if interview.status == InterviewStatus.COMPLETED:
                systems_used.append("interview_assessment")
        if contract is not None:
            systems_used.append("contract")

        body: dict[str, Any] = {
            "report_version": REPORT_VERSION,
            "report_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"matchit:transparency:{match.id}")),
            "issued_by": "MatchIT",
            "statement": _STATEMENT,
            "engagement": {
                "match_id": str(match.id),
                "assignment_id": str(match.assignment_id),
                "company": match.assignment.company.name,
                "specialist_reference": specialist_reference(match.specialist_id),
                "specialist_headline": match.specialist.headline,
                "assignment_summary": requirements.summary,
                "roles": [
                    {
                        "title": role.title,
                        "seniority": role.seniority,
                        "must_have_skills": role.must_have_skills,
                    }
                    for role in requirements.roles
                ],
            },
            "ranking": self._ranking_section(match, rank, considered),
            "interview": self._interview_section(interview),
            "decisions": self._decisions_section(match, contract),
            "ai_systems": [SYSTEMS_BY_KEY[key].card() for key in systems_used],
            "human_oversight": _HUMAN_OVERSIGHT,
            "your_rights": list(_RIGHTS),
        }
        return {
            **body,
            "signature": {"algorithm": SIGNATURE_ALGORITHM, "value": self.sign(body)},
        }

    def _ranking_section(self, match: Match, rank: int, considered: int) -> dict:
        system = SYSTEMS_BY_KEY["ranking"]
        components = []
        for name, weight in WEIGHTS.items():
            score = float(match.breakdown.get(name, 0.0))
            components.append(
                {
                    "component": name,
                    "weight": weight,
                    "score": round(score, 4),
                    "contribution": round(weight * score, 4),
                    "how_it_is_measured": RANKING_COMPONENT_DOC[name],
                }
            )
        return {
            "total_score": round(float(match.score), 4),
            "rank": rank,
            "candidates_scored": considered,
            "components": components,
            "method": (
                "A weighted sum of the components below, every one of which is "
                "computed by rule rather than by a model. No candidate is excluded "
                "before scoring."
            ),
            "system_key": system.key,
            "definition_fingerprint": system.fingerprint,
        }

    def _interview_section(self, interview: Interview | None) -> dict | None:
        if interview is None:
            return None
        plan = InterviewPlan.model_validate(interview.plan)
        scores = {
            entry["question"]: entry
            for entry in (interview.assessment or {}).get("per_question", [])
        }
        answers = {entry["question"]: entry for entry in interview.transcript}

        questions = []
        for question in plan.questions:
            answered = answers.get(question.question)
            scored = scores.get(question.question)
            questions.append(
                {
                    "question": question.question,
                    "skill": question.skill,
                    "asked_because": question.rationale,
                    "answered": answered is not None,
                    "answer_input_mode": (answered or {}).get("input_mode", "text"),
                    "score": scored["score"] if scored else None,
                    "reasoning": scored["reasoning"] if scored else None,
                }
            )

        assessment = interview.assessment or {}
        return {
            "conducted": True,
            "completed": interview.status == InterviewStatus.COMPLETED,
            "modality": (
                "Written answers. A spoken answer is transcribed to text and the text "
                "is what gets scored; no audio or video is retained or analysed."
            ),
            "scored_on": (
                "Content only. Delivery, accent, fluency, pace, personality and affect "
                "are excluded, and transcription artefacts must not affect a score."
            ),
            "gap_summary": plan.gap_summary,
            "questions": questions,
            "overall_score": assessment.get("overall_score"),
            "strengths": assessment.get("strengths", []),
            "development_areas": assessment.get("development_areas", []),
            "concerns": assessment.get("concerns", []),
            "recommendation": assessment.get("recommendation"),
            "summary": assessment.get("summary"),
            "system_keys": ["interview_plan", "interview_assessment"],
        }

    def _decisions_section(self, match: Match, contract: Contract | None) -> list[dict]:
        def entry(party: str, decision: Decision, at: datetime | None) -> dict:
            return {
                "party": party,
                "decision": decision.value,
                "decided_at": _iso(at),
                "made_by": "a person" if decision != Decision.PENDING else None,
            }

        decisions = [
            entry("company", match.company_decision, match.company_decided_at),
            entry("specialist", match.specialist_decision, match.specialist_decided_at),
        ]
        if contract is not None:
            signatures = [contract.company_signed_at, contract.specialist_signed_at]
            # The engagement is decided by the *second* signature, not the first.
            settled = max((at for at in signatures if at is not None), default=None)
            decisions.append(
                {
                    "party": "both",
                    "decision": f"contract {contract.status.value}",
                    "decided_at": settled.isoformat() if settled is not None else None,
                    "made_by": "a person on each side, by signature",
                    "company_signed_at": _iso(contract.company_signed_at),
                    "specialist_signed_at": _iso(contract.specialist_signed_at),
                }
            )
        return decisions


def report_markdown(report: dict) -> str:
    """Render a report as the document a human actually reads.

    Deterministic: the JSON is the record, this is a view of it, and nothing here
    may state anything the JSON does not.
    """
    engagement = report["engagement"]
    ranking = report["ranking"]
    lines = [
        "# AI transparency report",
        "",
        f"**Report ID:** `{report['report_id']}`  ",
        f"**Candidate reference:** {engagement['specialist_reference']}  ",
        f"**Company:** {engagement['company']}  ",
        f"**Assignment:** {engagement['assignment_summary']}",
        "",
        report["statement"],
        "",
        "## How this candidate was ranked",
        "",
        f"Score **{ranking['total_score']:.2f}** — ranked "
        f"**{ranking['rank']} of {ranking['candidates_scored']}** candidates scored.",
        "",
        ranking["method"],
        "",
        "| Component | Weight | Score | Contribution | How it is measured |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for component in ranking["components"]:
        lines.append(
            f"| {component['component']} | {component['weight']:.2f} | "
            f"{component['score']:.2f} | {component['contribution']:.3f} | "
            f"{component['how_it_is_measured']} |"
        )
    lines += ["", f"Ranking definition fingerprint: `{ranking['definition_fingerprint']}`", ""]

    interview = report.get("interview")
    if interview is None:
        lines += ["## Interview", "", "No screening interview was conducted.", ""]
    else:
        lines += [
            "## Interview",
            "",
            f"*{interview['modality']}*",
            "",
            f"*Scored on:* {interview['scored_on']}",
            "",
            f"**Why these questions:** {interview['gap_summary']}",
            "",
        ]
        for index, question in enumerate(interview["questions"], start=1):
            score = question["score"]
            lines += [
                f"### {index}. {question['question']}",
                "",
                f"- **Skill probed:** {question['skill']}",
                f"- **Asked because:** {question['asked_because']}",
                f"- **Answer given:** {'yes' if question['answered'] else 'no'}"
                f" ({question['answer_input_mode']})",
                f"- **Score:** {f'{score:.2f}' if score is not None else 'not scored'}",
            ]
            if question["reasoning"]:
                lines.append(f"- **Reasoning:** {question['reasoning']}")
            lines.append("")
        if interview["overall_score"] is not None:
            lines += [
                f"**Overall interview score:** {interview['overall_score']:.2f}  ",
                f"**Recommendation to the hiring manager:** {interview['recommendation']}",
                "",
            ]
        for heading, key in (
            ("Strengths", "strengths"),
            ("Development areas", "development_areas"),
            ("Concerns raised with the hiring manager", "concerns"),
        ):
            if interview.get(key):
                lines += [f"**{heading}**", ""]
                lines += [f"- {item}" for item in interview[key]]
                lines.append("")

    lines += [
        "## Decisions",
        "",
        "| Party | Decision | When | Made by |",
        "| --- | --- | --- | --- |",
    ]
    for decision in report["decisions"]:
        lines.append(
            f"| {decision['party']} | {decision['decision']} | "
            f"{decision['decided_at'] or '—'} | {decision['made_by'] or '—'} |"
        )

    lines += ["", "## Human oversight", "", report["human_oversight"], ""]
    lines += [
        "## AI systems involved",
        "",
        "| System | Kind | Fingerprint |",
        "| --- | --- | --- |",
    ]
    for system in report["ai_systems"]:
        lines.append(
            f"| {system['name']} | {system['kind']} | `{system['definition_fingerprint']}` |"
        )

    lines += ["", "## Your rights", ""]
    lines += [f"- {item}" for item in report["your_rights"]]
    lines += [
        "",
        "---",
        "",
        f"Signed with {report['signature']['algorithm']}: "
        f"`{report['signature']['value']}`",
        "",
        "Verify this document, unaltered, at `POST /api/v1/transparency-reports/verify`.",
    ]
    return "\n".join(lines) + "\n"
