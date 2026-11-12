"""Explicit initial policy; scores are ordinal indicators, not calibrated probabilities."""

from app.models.enums import BECType, RiskLevel
from app.schemas.analysis import DeterministicAssessment, ScoreBreakdown, SemanticAssessment
from app.services.alerts import ALERT_THRESHOLD

HYBRID_POLICY_VERSION = "hybrid-v2"


def combine_scores(
    deterministic_score: int, semantic_score: int, *, signal_codes: set[str] | None = None
) -> int:
    return build_score_breakdown(
        deterministic_score,
        semantic_score,
        signal_codes=signal_codes,
    ).final_score


def build_score_breakdown(
    deterministic_score: int,
    semantic_score: int,
    *,
    signal_codes: set[str] | None = None,
    raw_deterministic_total: int | None = None,
    alert_threshold: int = ALERT_THRESHOLD,
) -> ScoreBreakdown:
    if any(type(s) is not int or not 0 <= s <= 100 for s in (deterministic_score, semantic_score)):
        raise ValueError("Scores must be integers between 0 and 100")
    if type(alert_threshold) is not int or not 0 <= alert_threshold <= 100:
        raise ValueError("Alert threshold must be an integer between 0 and 100")
    if raw_deterministic_total is None:
        raw_deterministic_total = deterministic_score
    if type(raw_deterministic_total) is not int or raw_deterministic_total < 0:
        raise ValueError("Raw deterministic total must be a non-negative integer")
    # Equal weights; integer half-up rounding, with a floor only for strong
    # deterministic evidence so a contradictory LLM cannot erase it.
    weighted = (deterministic_score + semantic_score + 1) // 2
    codes = signal_codes or set()
    floor = 0
    floor_reasons: list[str] = []
    if deterministic_score >= 70:
        floor = 70
        floor_reasons.append("DETERMINISTIC_SCORE_GE_70")
    if "IMPERSONATION_SENSITIVE_REQUEST" in codes:
        floor = max(floor, 70)
        floor_reasons.append("IMPERSONATION_SENSITIVE_REQUEST")
    if "IMPERSONATION_REQUEST" in codes:
        floor = max(floor, 50)
        floor_reasons.append("IMPERSONATION_REQUEST")
    final_score = max(weighted, floor)
    return ScoreBreakdown(
        mode="COMPLETED",
        raw_deterministic_total=raw_deterministic_total,
        deterministic_score=deterministic_score,
        semantic_score=semantic_score,
        weighted_score=weighted,
        floor_score=floor,
        floor_reasons=floor_reasons,
        final_score=final_score,
        alert_threshold=alert_threshold,
        alert_triggered=final_score >= alert_threshold,
    )


def build_fallback_breakdown(
    deterministic_score: int,
    *,
    raw_deterministic_total: int,
    alert_threshold: int = ALERT_THRESHOLD,
) -> ScoreBreakdown:
    if type(deterministic_score) is not int or not 0 <= deterministic_score <= 100:
        raise ValueError("Scores must be integers between 0 and 100")
    if type(raw_deterministic_total) is not int or raw_deterministic_total < 0:
        raise ValueError("Raw deterministic total must be a non-negative integer")
    if type(alert_threshold) is not int or not 0 <= alert_threshold <= 100:
        raise ValueError("Alert threshold must be an integer between 0 and 100")
    return ScoreBreakdown(
        mode="FALLBACK",
        raw_deterministic_total=raw_deterministic_total,
        deterministic_score=deterministic_score,
        semantic_score=None,
        weighted_score=None,
        floor_score=0,
        floor_reasons=[],
        final_score=deterministic_score,
        alert_threshold=alert_threshold,
        alert_triggered=deterministic_score >= alert_threshold,
    )


def risk_level(score: int) -> RiskLevel:
    if type(score) is not int or not 0 <= score <= 100:
        raise ValueError("Risk score must be between 0 and 100")
    if score >= 85:
        return RiskLevel.CRITICAL
    if score >= 70:
        return RiskLevel.HIGH
    if score >= 40:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def resolve_bec_type(
    score: int, deterministic: DeterministicAssessment, semantic: SemanticAssessment
) -> BECType | None:
    if score < 40:
        return None
    # Concrete local evidence takes precedence. Semantic-only patterns remain
    # possible, including compromised legitimate accounts.
    return deterministic.bec_type or semantic.bec_type
