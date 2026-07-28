"""Engagement evidence pack: the file you want before anyone asks for it.

The Dutch enforcement moratorium on false self-employment ended in 2025 and the tax
authority can impose culpability penalties from 2026, which turns "can you show this
was a genuine independent engagement?" from a theoretical question into a dated one.
The evidence is not hard to produce — a contract, a defined scope, invoices, a
signature trail — it is just scattered, and nobody assembles it until the letter
arrives. MatchIT holds all of it in one place, so it assembles it now.

What this is not: a legal opinion. The Belastingdienst weighs the whole relationship
and no checklist decides the answer, so every indicator below reports what the
platform actually observed and says which way it points, and the pack refuses to
draw a conclusion. Anything that claimed to would be worth less than nothing to the
party relying on it.
"""

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import AssignmentRequirements, ContractDraft
from app.models import (
    Assignment,
    AuditAction,
    AuditLog,
    Contract,
    ContractStatus,
    Invoice,
    Match,
)

SUPPORTS = "supports_independence"
AGAINST = "points_the_other_way"
NEUTRAL = "neutral"

FULL_TIME_HOURS = 40

# Clause topics worth evidencing, and the words that identify them in a draft.
# Matched case-insensitively against headings and bodies, in English and Dutch,
# because the drafter writes in the language of the parties.
CLAUSE_TOPICS: dict[str, tuple[str, ...]] = {
    "contractor_status": (
        "dba",
        "zelfstandig",
        "schijnzelfstandig",
        "self-employ",
        "independent contractor",
        "contractor status",
        "employment relationship",
        "misclassification",
    ),
    "substitution": ("substitut", "vervang", "replacement", "delegate"),
    "own_equipment": ("own equipment", "own tools", "eigen middelen", "own materials", "hardware"),
    "intellectual_property": ("intellectual property", "intellectueel eigendom", "ip rights"),
    "confidentiality": ("confidential", "geheimhouding", "non-disclosure"),
    "termination": ("terminat", "opzeg", "notice period"),
    "data_protection": ("data protection", "gdpr", "avg", "personal data"),
}

_DISCLAIMER = (
    "This pack is evidence, not a determination. Whether an engagement is genuinely "
    "independent is judged on the relationship as a whole — how the work is actually "
    "directed day to day, how embedded the worker is in the organisation, and whether "
    "they work at their own account and risk. A document cannot establish facts that "
    "the working practice contradicts. Take this to your adviser; do not treat it as "
    "the answer."
)


@dataclass
class Indicator:
    key: str
    label: str
    observed: str
    direction: str
    why: str


def _clause_topics(draft: ContractDraft) -> dict[str, str | None]:
    """Which documented topics the draft actually covers, and under which heading."""
    found: dict[str, str | None] = {}
    for topic, keywords in CLAUSE_TOPICS.items():
        heading = None
        for clause in draft.clauses:
            haystack = f"{clause.heading}\n{clause.body}".lower()
            if any(keyword in haystack for keyword in keywords):
                heading = clause.heading
                break
        found[topic] = heading
    return found


class EvidencePackService:
    async def build(self, db: AsyncSession, match: Match, contract: Contract) -> dict:
        draft = ContractDraft.model_validate(contract.draft)
        requirements = AssignmentRequirements.model_validate(match.assignment.requirements)
        topics = _clause_topics(draft)
        invoices = list(
            await db.scalars(
                select(Invoice)
                .where(Invoice.contract_id == contract.id)
                .order_by(Invoice.period_start)
            )
        )
        clients = await self._distinct_clients(db, match)
        signatures = await self._signature_trail(db, contract)

        indicators = self._indicators(
            contract=contract,
            draft=draft,
            requirements=requirements,
            topics=topics,
            invoices=invoices,
            distinct_clients=clients,
        )
        tally = {
            direction: sum(1 for item in indicators if item.direction == direction)
            for direction in (SUPPORTS, AGAINST, NEUTRAL)
        }

        return {
            "pack_version": "1",
            "jurisdiction": self._jurisdiction(match, contract),
            "disclaimer": _DISCLAIMER,
            "engagement": {
                "match_id": str(match.id),
                "contract_id": str(contract.id),
                "company": match.assignment.company.name,
                "company_country": match.assignment.company.country,
                "specialist_headline": match.specialist.headline,
                "specialist_country": match.specialist.country,
                "status": contract.status.value,
                "start_date": contract.start_date.isoformat(),
                "end_date": contract.end_date.isoformat() if contract.end_date else None,
                "hourly_rate": float(contract.hourly_rate),
                "currency": contract.currency,
                "hours_per_week": contract.hours_per_week,
            },
            "assignment": {
                "summary": requirements.summary,
                "roles": [role.title for role in requirements.roles],
                "duration_weeks": requirements.duration_weeks,
            },
            "scope_of_work": list(draft.scope_of_work),
            "contract_terms": {
                "title": draft.title,
                "rate_terms": draft.rate_terms,
                "duration_terms": draft.duration_terms,
                "governing_law": draft.governing_law,
                "clauses": [
                    {"heading": clause.heading, "body": clause.body} for clause in draft.clauses
                ],
                "open_points": list(draft.open_points),
            },
            "clause_coverage": topics,
            "signatures": {
                "company_signed_at": (
                    contract.company_signed_at.isoformat()
                    if contract.company_signed_at
                    else None
                ),
                "specialist_signed_at": (
                    contract.specialist_signed_at.isoformat()
                    if contract.specialist_signed_at
                    else None
                ),
                "fully_signed": contract.is_fully_signed,
                "audit_trail": signatures,
            },
            "invoices": [
                {
                    "id": str(invoice.id),
                    "status": invoice.status.value,
                    "period_start": invoice.period_start.isoformat(),
                    "period_end": invoice.period_end.isoformat(),
                    "hours": float(invoice.hours),
                    "hourly_rate": float(invoice.hourly_rate),
                    "subtotal": float(invoice.subtotal),
                    "vat_treatment": invoice.vat_treatment,
                    "vat_amount": float(invoice.vat_amount),
                    "total": float(invoice.total),
                    "currency": invoice.currency,
                }
                for invoice in invoices
            ],
            "indicators": [asdict(indicator) for indicator in indicators],
            "indicator_tally": tally,
        }

    def _jurisdiction(self, match: Match, contract: Contract) -> dict[str, Any]:
        countries = {match.assignment.company.country.upper(), match.specialist.country.upper()}
        dutch = "NL" in countries
        return {
            "countries": sorted(countries),
            "primary_regime": "NL — Wet DBA" if dutch else "EU — general misclassification risk",
            "note": (
                "The Dutch enforcement moratorium ended in 2025 and culpability penalties "
                "apply from 2026, so this pack is framed against the Wet DBA criteria."
                if dutch
                else "Neither party is in the Netherlands. The indicators below are the "
                "Dutch Wet DBA criteria, which track the factors most EU "
                "misclassification tests weigh; check your own jurisdiction's."
            ),
        }

    async def _distinct_clients(self, db: AsyncSession, match: Match) -> int:
        """How many separate companies this specialist has contracted with here.

        A single client is the classic misclassification pattern, so the count is
        reported honestly whichever way it points — and it counts only what this
        platform can see, which is stated in the indicator itself.
        """
        return int(
            await db.scalar(
                select(func.count(distinct(Assignment.company_id)))
                .select_from(Contract)
                .join(Match, Contract.match_id == Match.id)
                .join(Assignment, Match.assignment_id == Assignment.id)
                .where(
                    Match.specialist_id == match.specialist_id,
                    Contract.status.in_(
                        [ContractStatus.ACTIVE, ContractStatus.COMPLETED]
                    ),
                )
            )
            or 0
        )

    async def _signature_trail(self, db: AsyncSession, contract: Contract) -> list[dict]:
        rows = await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.action == AuditAction.CONTRACT_SIGNED,
                AuditLog.target_id == contract.id,
            )
            .order_by(AuditLog.created_at)
        )
        return [
            {
                "at": row.created_at.isoformat(),
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "client_ip": row.client_ip,
                "context": row.context,
            }
            for row in rows
        ]

    def _indicators(
        self,
        *,
        contract: Contract,
        draft: ContractDraft,
        requirements: AssignmentRequirements,
        topics: dict[str, str | None],
        invoices: list[Invoice],
        distinct_clients: int,
    ) -> list[Indicator]:
        indicators: list[Indicator] = []

        if contract.end_date is not None:
            indicators.append(
                Indicator(
                    key="fixed_term",
                    label="Defined end date",
                    observed=f"{contract.start_date.isoformat()} to "
                    f"{contract.end_date.isoformat()}",
                    direction=SUPPORTS,
                    why="A dated engagement for a defined result reads as a project, "
                    "not as open-ended employment.",
                )
            )
        else:
            indicators.append(
                Indicator(
                    key="fixed_term",
                    label="Defined end date",
                    observed="open-ended",
                    direction=AGAINST,
                    why="An engagement with no end date is harder to distinguish from "
                    "an employment relationship the longer it runs.",
                )
            )

        indicators.append(
            Indicator(
                key="commitment",
                label="Weekly hours",
                observed=f"{contract.hours_per_week} hours per week",
                direction=SUPPORTS if contract.hours_per_week < FULL_TIME_HOURS else NEUTRAL,
                why=(
                    "Below a full working week leaves room for other clients, which "
                    "speaks to working at own account and risk."
                    if contract.hours_per_week < FULL_TIME_HOURS
                    else "A full week is normal for project work and is not itself a "
                    "problem, but it does not evidence independence either."
                ),
            )
        )

        indicators.append(
            Indicator(
                key="defined_scope",
                label="Scope of work",
                observed=f"{len(draft.scope_of_work)} defined deliverable(s)",
                direction=SUPPORTS if len(draft.scope_of_work) >= 2 else NEUTRAL,
                why="A contracted result is evidence that the specialist is engaged "
                "for an outcome rather than placed under direction.",
            )
        )

        if distinct_clients >= 2:
            indicators.append(
                Indicator(
                    key="multiple_clients",
                    label="Clients on this platform",
                    observed=f"{distinct_clients} distinct companies",
                    direction=SUPPORTS,
                    why="Serving several clients is one of the strongest indicators of "
                    "genuine entrepreneurship.",
                )
            )
        else:
            indicators.append(
                Indicator(
                    key="multiple_clients",
                    label="Clients on this platform",
                    observed=f"{distinct_clients} distinct company on MatchIT",
                    direction=NEUTRAL,
                    why="MatchIT sees only engagements arranged here. Work done "
                    "elsewhere counts just as much and belongs in this pack — add it "
                    "from your own records.",
                )
            )

        rate_terms = draft.rate_terms.lower()
        indicators.append(
            Indicator(
                key="rate_agreed_commercially",
                label="Rate",
                observed=f"{float(contract.hourly_rate):.2f} {contract.currency} per hour, "
                f"agreed before signature",
                direction=SUPPORTS if "invoice" in rate_terms or invoices else NEUTRAL,
                why="A rate negotiated between the parties and invoiced by the "
                "specialist is commercial, not salaried.",
            )
        )

        if invoices:
            periods = (
                f"{invoices[0].period_start.isoformat()} to "
                f"{invoices[-1].period_end.isoformat()}"
            )
            treatments = sorted({invoice.vat_treatment for invoice in invoices})
            indicators.append(
                Indicator(
                    key="own_invoicing",
                    label="Invoices issued by the specialist",
                    observed=f"{len(invoices)} invoice(s), {periods}, VAT treatment: "
                    f"{', '.join(treatments)}",
                    direction=SUPPORTS,
                    why="Invoicing in their own name, with VAT handled as a business "
                    "supply, is how an independent contractor is paid.",
                )
            )
        else:
            indicators.append(
                Indicator(
                    key="own_invoicing",
                    label="Invoices issued by the specialist",
                    observed="none yet",
                    direction=NEUTRAL,
                    why="No period has been billed through the platform yet.",
                )
            )

        for topic, (label, direction_when_present, why) in _CLAUSE_INDICATORS.items():
            heading = topics.get(topic)
            indicators.append(
                Indicator(
                    key=f"clause_{topic}",
                    label=label,
                    observed=f"present — “{heading}”" if heading else "absent",
                    direction=direction_when_present if heading else NEUTRAL,
                    why=why,
                )
            )

        if draft.open_points:
            indicators.append(
                Indicator(
                    key="open_points",
                    label="Points left for a lawyer",
                    observed=f"{len(draft.open_points)} open point(s)",
                    direction=NEUTRAL,
                    why="The drafter flags what it will not decide rather than "
                    "guessing. Resolve these before relying on the contract.",
                )
            )

        return indicators


_CLAUSE_INDICATORS: dict[str, tuple[str, str, str]] = {
    "contractor_status": (
        "Contractor-status clause",
        SUPPORTS,
        "The parties addressed the nature of the relationship explicitly rather than "
        "leaving it to be inferred.",
    ),
    "substitution": (
        "Right of substitution",
        SUPPORTS,
        "A right to be replaced is incompatible with the personal-service obligation "
        "that characterises employment.",
    ),
    "own_equipment": (
        "Own equipment and materials",
        SUPPORTS,
        "Working with one's own tools speaks to own account and risk.",
    ),
    "intellectual_property": (
        "Intellectual property assignment",
        SUPPORTS,
        "IP has to be assigned by contract precisely because the specialist is not an "
        "employee, whose work product would vest automatically.",
    ),
    "confidentiality": (
        "Confidentiality",
        NEUTRAL,
        "Standard in both employment and commercial engagements; recorded for "
        "completeness.",
    ),
    "termination": (
        "Termination and notice",
        NEUTRAL,
        "Recorded so the agreed exit terms are in the pack.",
    ),
    "data_protection": (
        "Data protection",
        NEUTRAL,
        "Recorded because GDPR obligations follow the work, not the employment status.",
    ),
}


def evidence_pack_markdown(pack: dict) -> str:
    """The pack as a document to hand to an adviser."""
    engagement = pack["engagement"]
    lines = [
        "# Engagement evidence pack",
        "",
        f"**Company:** {engagement['company']} ({engagement['company_country']})  ",
        f"**Specialist:** {engagement['specialist_headline']} "
        f"({engagement['specialist_country']})  ",
        f"**Contract:** `{engagement['contract_id']}` — {engagement['status']}  ",
        f"**Term:** {engagement['start_date']} to {engagement['end_date'] or 'open-ended'}  ",
        f"**Terms:** {engagement['hourly_rate']:.2f} {engagement['currency']}/hour, "
        f"{engagement['hours_per_week']} hours per week",
        "",
        f"**Regime:** {pack['jurisdiction']['primary_regime']} — {pack['jurisdiction']['note']}",
        "",
        "> " + pack["disclaimer"].replace("\n", "\n> "),
        "",
        "## Assignment",
        "",
        pack["assignment"]["summary"],
        "",
        "## Contracted scope of work",
        "",
    ]
    lines += [f"- {item}" for item in pack["scope_of_work"]]

    tally = pack["indicator_tally"]
    lines += [
        "",
        "## Independence indicators",
        "",
        f"{tally[SUPPORTS]} support independence, {tally[AGAINST]} point the other way, "
        f"{tally[NEUTRAL]} are neutral. The count is a summary, not a score — the "
        "indicators are weighed as a whole, not added up.",
        "",
        "| Indicator | Observed | Direction | Why it matters |",
        "| --- | --- | --- | --- |",
    ]
    for indicator in pack["indicators"]:
        lines.append(
            f"| {indicator['label']} | {indicator['observed']} | "
            f"{indicator['direction'].replace('_', ' ')} | {indicator['why']} |"
        )

    lines += ["", "## Signatures", ""]
    signatures = pack["signatures"]
    lines += [
        f"- Company signed: {signatures['company_signed_at'] or 'not signed'}",
        f"- Specialist signed: {signatures['specialist_signed_at'] or 'not signed'}",
    ]
    for entry in signatures["audit_trail"]:
        lines.append(f"- Audit: signature recorded at {entry['at']} from {entry['client_ip']}")

    lines += ["", "## Invoices", ""]
    if pack["invoices"]:
        lines += [
            "| Period | Hours | Rate | Subtotal | VAT | Total |",
            "| --- | ---: | ---: | ---: | --- | ---: |",
        ]
        for invoice in pack["invoices"]:
            lines.append(
                f"| {invoice['period_start']} – {invoice['period_end']} | "
                f"{invoice['hours']:.2f} | {invoice['hourly_rate']:.2f} | "
                f"{invoice['subtotal']:.2f} | {invoice['vat_treatment']} "
                f"{invoice['vat_amount']:.2f} | {invoice['total']:.2f} |"
            )
    else:
        lines.append("No periods have been billed through the platform yet.")

    lines += ["", "## Contract clauses", ""]
    for clause in pack["contract_terms"]["clauses"]:
        lines += [f"### {clause['heading']}", "", clause["body"], ""]
    if pack["contract_terms"]["open_points"]:
        lines += ["### Open points for a lawyer", ""]
        lines += [f"- {item}" for item in pack["contract_terms"]["open_points"]]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
