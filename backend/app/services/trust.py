"""Dynamic trust score: 0-100, weighted factors, persisted breakdown."""

from dataclasses import dataclass

WEIGHTS = {
    "identity_verified": 0.20,
    "reviews": 0.20,
    "projects_completed": 0.15,
    "response_time": 0.10,
    "interview_score": 0.15,
    "payment_history": 0.10,
    "certifications_validated": 0.10,
}


@dataclass
class TrustSignals:
    identity_verified: bool = False
    average_review: float | None = None  # 1-5 stars
    review_count: int = 0
    projects_completed: int = 0
    median_response_minutes: float | None = None
    interview_score: float | None = None  # 0-1 from AI interviews
    payments_on_time: int = 0
    payments_total: int = 0
    certifications_validated: int = 0
    certifications_total: int = 0


def _review_factor(signals: TrustSignals) -> float:
    if signals.average_review is None or signals.review_count == 0:
        return 0.0
    stars = (signals.average_review - 1.0) / 4.0
    # confidence ramps up over the first 10 reviews
    confidence = min(1.0, signals.review_count / 10.0)
    return stars * confidence


def _response_factor(signals: TrustSignals) -> float:
    if signals.median_response_minutes is None:
        return 0.0
    if signals.median_response_minutes <= 60:
        return 1.0
    if signals.median_response_minutes >= 24 * 60:
        return 0.0
    return 1.0 - (signals.median_response_minutes - 60) / (24 * 60 - 60)


class TrustScoreService:
    def compute(self, signals: TrustSignals) -> tuple[float, dict[str, float]]:
        """Return (score 0-100, per-factor breakdown each 0-1)."""
        breakdown = {
            "identity_verified": 1.0 if signals.identity_verified else 0.0,
            "reviews": _review_factor(signals),
            "projects_completed": min(1.0, signals.projects_completed / 10.0),
            "response_time": _response_factor(signals),
            "interview_score": signals.interview_score or 0.0,
            "payment_history": (
                signals.payments_on_time / signals.payments_total if signals.payments_total else 0.0
            ),
            "certifications_validated": (
                signals.certifications_validated / signals.certifications_total
                if signals.certifications_total
                else 0.0
            ),
        }
        score = 100.0 * sum(WEIGHTS[k] * v for k, v in breakdown.items())
        return round(score, 1), breakdown
