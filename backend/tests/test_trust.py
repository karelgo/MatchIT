from app.services.trust import TrustScoreService, TrustSignals


def test_empty_signals_score_zero():
    score, breakdown = TrustScoreService().compute(TrustSignals())
    assert score == 0.0
    assert all(v == 0.0 for v in breakdown.values())


def test_strong_profile_scores_high():
    signals = TrustSignals(
        identity_verified=True,
        average_review=4.8,
        review_count=25,
        projects_completed=12,
        median_response_minutes=30,
        interview_score=0.9,
        payments_on_time=10,
        payments_total=10,
        certifications_validated=3,
        certifications_total=3,
    )
    score, breakdown = TrustScoreService().compute(signals)
    assert score > 90
    assert breakdown["identity_verified"] == 1.0
    assert breakdown["payment_history"] == 1.0


def test_review_confidence_ramps_with_count():
    service = TrustScoreService()
    few, _ = service.compute(TrustSignals(average_review=5.0, review_count=2))
    many, _ = service.compute(TrustSignals(average_review=5.0, review_count=20))
    assert many > few


def test_slow_response_penalised():
    service = TrustScoreService()
    fast, _ = service.compute(TrustSignals(median_response_minutes=10))
    slow, _ = service.compute(TrustSignals(median_response_minutes=20 * 60))
    assert fast > slow
    assert score_bounds_ok(fast) and score_bounds_ok(slow)


def score_bounds_ok(score: float) -> bool:
    return 0.0 <= score <= 100.0
