import pytest

from app.models.enums import BECType, RiskLevel
from app.schemas.analysis import DeterministicAssessment, SemanticAssessment
from app.services.hybrid_scoring import (
    build_fallback_breakdown,
    build_score_breakdown,
    combine_scores,
    resolve_bec_type,
    risk_level,
)


@pytest.mark.parametrize(
    "det,sem,expected",
    [
        (0, 0, 0),
        (0, 100, 50),
        (100, 0, 70),
        (70, 0, 70),
        (69, 0, 35),
        (60, 80, 70),
        (90, 90, 90),
        (100, 100, 100),
        (8, 9, 9),
    ],
)
def test_combine_scores(det, sem, expected):
    assert combine_scores(det, sem) == expected


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, RiskLevel.LOW),
        (39, RiskLevel.LOW),
        (40, RiskLevel.MEDIUM),
        (69, RiskLevel.MEDIUM),
        (70, RiskLevel.HIGH),
        (84, RiskLevel.HIGH),
        (85, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_thresholds(score, expected):
    assert risk_level(score) == expected


@pytest.mark.parametrize("score", [-1, 101, True, 2.5, "50", None])
def test_invalid_scores(score):
    with pytest.raises(ValueError):
        risk_level(score)
    with pytest.raises(ValueError):
        combine_scores(score, 10)
    with pytest.raises(ValueError):
        combine_scores(10, score)


def test_type_resolution():
    det = DeterministicAssessment(score=50, bec_type=BECType.VENDOR_FRAUD, signals=[])
    sem = SemanticAssessment(
        risk_score=80,
        bec_type=BECType.OTHER,
        signals=[],
        summary="Evidence",
        recommended_action="Verify",
    )
    assert resolve_bec_type(39, det, sem) is None
    assert resolve_bec_type(40, det, sem) == BECType.VENDOR_FRAUD
    det.bec_type = None
    assert resolve_bec_type(70, det, sem) == BECType.OTHER
    sem.bec_type = None
    assert resolve_bec_type(70, det, sem) is None


@pytest.mark.parametrize(
    "det,sem,codes,expected",
    [
        (35, 0, {"IMPERSONATION_REQUEST"}, 50),
        (35, 0, {"IMPERSONATION_SENSITIVE_REQUEST"}, 70),
        (69, 0, set(), 35),
        (70, 0, set(), 70),
        (0, 99, set(), 50),
    ],
)
def test_security_floors_are_independent_from_semantic_score(det, sem, codes, expected):
    assert combine_scores(det, sem, signal_codes=codes) == expected


def test_score_breakdown_reconstructs_cap_average_and_floor():
    breakdown = build_score_breakdown(
        100,
        42,
        signal_codes={"IMPERSONATION_SENSITIVE_REQUEST"},
        raw_deterministic_total=114,
    )
    assert breakdown.raw_deterministic_total == 114
    assert breakdown.deterministic_score == 100
    assert breakdown.weighted_score == 71
    assert breakdown.floor_score == 70
    assert breakdown.final_score == 71
    assert breakdown.alert_triggered is True


def test_fallback_breakdown_has_no_semantic_path():
    breakdown = build_fallback_breakdown(58, raw_deterministic_total=114)
    assert breakdown.mode == "FALLBACK"
    assert breakdown.semantic_score is None
    assert breakdown.weighted_score is None
    assert breakdown.final_score == 58
    assert breakdown.alert_triggered is True
