"""Specialist-facing feedback: why this match went the way it did.

Every other platform sends silence. Silence is cheap for the platform and
corrosive for the person on the other end, and it is also the thing candidates
complain about most. MatchIT already computes the entire answer — the score
breakdown is persisted with every match — so withholding it would be a choice, not
a limitation.

Nothing here calls a model. The explanation is derived from the same persisted
numbers the company saw, which means it is free, instant, always available, and
structurally incapable of inventing a reason that was not the real one.
"""

from dataclasses import dataclass, field
from datetime import date

from app.ai.schemas import AssignmentRequirements
from app.models import Decision, Interview, InterviewStatus, Match, MatchStatus, SpecialistProfile
from app.services.aisystems import RANKING_COMPONENT_DOC
from app.services.matching import WEIGHTS

# Below this, a component is worth telling someone about; above it, it is noise.
NOTABLE_LOSS = 0.01
STRONG_SCORE = 0.8


@dataclass
class Factor:
    component: str
    weight: float
    score: float
    points_lost: float
    what_it_measures: str
    what_happened: str
    what_would_help: str | None = None


@dataclass
class Feedback:
    match_id: str
    outcome: str
    headline: str
    total_score: float
    rank: int
    candidates_scored: int
    cost_you_most: list[Factor] = field(default_factory=list)
    worked_in_your_favour: list[Factor] = field(default_factory=list)
    interview_strengths: list[str] = field(default_factory=list)
    interview_development_areas: list[str] = field(default_factory=list)
    interview_score: float | None = None
    note: str = ""


_OUTCOMES = {
    "not_selected": (
        "not_selected",
        "The company reviewed your profile and chose not to proceed.",
    ),
    "declined": ("declined", "You declined this opportunity."),
    "matched": ("matched", "You and the company both accepted — this became a mutual match."),
    "awaiting_you": ("awaiting_you", "The company accepted. This one is waiting on you."),
}

_NOTE = (
    "This is the same breakdown the company saw, not a version written for you. A low "
    "score on a component is a statement about the data on your profile, not a judgement "
    "of your ability — most of it you can change today."
)


def _missing_skills(
    requirements: AssignmentRequirements, profile: SpecialistProfile
) -> list[str]:
    must, _ = requirements.all_skills()
    claimed = {skill["name"].lower() for skill in profile.skills}
    return [skill for skill in must if skill not in claimed]


def _skills_detail(
    requirements: AssignmentRequirements, profile: SpecialistProfile
) -> tuple[str, str | None]:
    must, _ = requirements.all_skills()
    missing = _missing_skills(requirements, profile)
    if not missing:
        return f"Your profile claims every must-have skill ({len(must)} of {len(must)}).", None
    listed = ", ".join(missing)
    return (
        f"{len(missing)} of {len(must)} must-have skills were not on your profile: {listed}.",
        "If you have worked with these, add them — or import your CV or GitHub, which "
        "attaches evidence to each one and outranks a self-reported claim.",
    )


def _rate_detail(
    requirements: AssignmentRequirements, profile: SpecialistProfile
) -> tuple[str, str | None]:
    ceiling = requirements.budget.max_hourly
    rate = profile.hourly_rate
    if rate is None:
        return (
            "You have not set an hourly rate, so this scored neutrally.",
            "Setting a rate lets the engine score you properly instead of splitting "
            "the difference.",
        )
    if ceiling is None:
        return "The assignment carried no stated budget ceiling, so this scored neutrally.", None
    if rate <= ceiling:
        return f"Your rate of {rate:.0f} was within the ceiling of {ceiling:.0f}.", None
    over = (rate - ceiling) / ceiling
    return (
        f"Your rate of {rate:.0f} was {over:.0%} above this assignment's ceiling "
        f"of {ceiling:.0f}.",
        "Nothing to fix if that is your rate — this assignment was priced below it.",
    )


def _availability_detail(
    requirements: AssignmentRequirements, profile: SpecialistProfile, today: date
) -> tuple[str, str | None]:
    start = requirements.start_date
    available = profile.available_from
    if start is None:
        return "The assignment gave no start date, so availability barely mattered.", None
    if available is None:
        return (
            f"You have no availability date set; the assignment starts {start.isoformat()}.",
            "Set your available-from date. An empty field is read as available now, "
            "which is a guess the engine should not have to make.",
        )
    if available <= start:
        return f"You were available by the start date ({start.isoformat()}).", None
    weeks = (available - start).days / 7.0
    return (
        f"You come free on {available.isoformat()}, about {weeks:.0f} week(s) after this "
        f"assignment starts ({start.isoformat()}).",
        "Keep your available-from date current — a stale one costs you matches you "
        "could actually take.",
    )


def _location_detail(
    requirements: AssignmentRequirements, profile: SpecialistProfile
) -> tuple[str, str | None]:
    if requirements.remote_allowed:
        return "The assignment allowed remote work, so location did not count against you.", None
    if profile.remote_preference.value == "remote":
        return (
            "This assignment required on-site presence and your profile is remote-only.",
            "If you would travel for the right engagement, set your preference to "
            "hybrid and give a travel distance.",
        )
    if requirements.country and requirements.country.upper() != profile.country.upper():
        return (
            f"This assignment is on-site in {requirements.country.upper()} and your "
            f"profile is in {profile.country.upper()}.",
            None,
        )
    return "Your location and working preference fitted the assignment.", None


def _language_detail(
    requirements: AssignmentRequirements, profile: SpecialistProfile
) -> tuple[str, str | None]:
    required = {code.lower() for code in requirements.languages}
    if not required:
        return "The assignment named no required working language.", None
    spoken = {code.lower() for code in profile.languages}
    missing = sorted(required - spoken)
    if not missing:
        return f"You speak every required working language ({', '.join(sorted(required))}).", None
    return (
        f"Required working language(s) not listed on your profile: {', '.join(missing)}.",
        "If you work in these languages, add them — the engine only knows what the "
        "profile says.",
    )


def _semantic_detail(profile: SpecialistProfile) -> tuple[str, str | None]:
    thin = len(profile.bio.strip()) < 200
    what = (
        "Your profile text and this assignment's description had little in common, "
        "which is measured on the words themselves rather than on your skills list."
    )
    if thin:
        return what, (
            "Your bio is short. A few paragraphs on the systems you have actually "
            "built — the scale, the stack, the problem — is the single highest-value "
            "edit available to you."
        )
    return what, "This assignment simply described a different kind of work."


def build(
    match: Match,
    requirements: AssignmentRequirements,
    profile: SpecialistProfile,
    interview: Interview | None,
    *,
    rank: int,
    candidates_scored: int,
    today: date | None = None,
) -> Feedback:
    today = today or date.today()
    details = {
        "skills": _skills_detail(requirements, profile),
        "semantic": _semantic_detail(profile),
        "rate": _rate_detail(requirements, profile),
        "availability": _availability_detail(requirements, profile, today),
        "location": _location_detail(requirements, profile),
        "language": _language_detail(requirements, profile),
    }

    factors = []
    for component, weight in WEIGHTS.items():
        score = float(match.breakdown.get(component, 0.0))
        what_happened, what_would_help = details[component]
        factors.append(
            Factor(
                component=component,
                weight=weight,
                score=round(score, 4),
                points_lost=round(weight * (1.0 - score), 4),
                what_it_measures=RANKING_COMPONENT_DOC[component],
                what_happened=what_happened,
                what_would_help=what_would_help,
            )
        )

    cost_most = sorted(
        (factor for factor in factors if factor.points_lost > NOTABLE_LOSS),
        key=lambda factor: factor.points_lost,
        reverse=True,
    )
    favour = sorted(
        (factor for factor in factors if factor.score >= STRONG_SCORE),
        key=lambda factor: factor.weight * factor.score,
        reverse=True,
    )

    if match.company_decision == Decision.REJECTED:
        outcome, headline = _OUTCOMES["not_selected"]
    elif match.specialist_decision == Decision.REJECTED:
        outcome, headline = _OUTCOMES["declined"]
    elif match.status == MatchStatus.MUTUAL:
        outcome, headline = _OUTCOMES["matched"]
    else:
        outcome, headline = _OUTCOMES["awaiting_you"]

    # Interview feedback stays constructive here. The full assessment, concerns
    # included, is not hidden — it is in the transparency report for the same
    # match; this view is the coaching summary, not a redaction of it.
    strengths: list[str] = []
    development: list[str] = []
    interview_score = None
    if interview is not None and interview.status == InterviewStatus.COMPLETED:
        assessment = interview.assessment or {}
        strengths = list(assessment.get("strengths", []))
        development = list(assessment.get("development_areas", []))
        interview_score = assessment.get("overall_score")

    return Feedback(
        match_id=str(match.id),
        outcome=outcome,
        headline=headline,
        total_score=round(float(match.score), 4),
        rank=rank,
        candidates_scored=candidates_scored,
        cost_you_most=cost_most[:3],
        worked_in_your_favour=favour[:3],
        interview_strengths=strengths,
        interview_development_areas=development,
        interview_score=interview_score,
        note=_NOTE,
    )
