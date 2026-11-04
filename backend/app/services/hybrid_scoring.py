"""Explicit initial policy; scores are ordinal indicators, not calibrated probabilities."""

from app.models.enums import BECType, RiskLevel
from app.schemas.analysis import DeterministicAssessment, SemanticAssessment

HYBRID_POLICY_VERSION = "hybrid-v2"


def combine_scores(
    deterministic_score: int, semantic_score: int, *, signal_codes: set[str] | None = None
) -> int:
    if any(type(s) is not int or not 0 <= s <= 100 for s in (deterministic_score, semantic_score)):
        raise ValueError("Scores must be integers between 0 and 100")
    # Equal weights; integer half-up rounding, with a floor only for strong
    # deterministic evidence so a contradictory LLM cannot erase it.
    weighted = (deterministic_score + semantic_score + 1) // 2
    codes = signal_codes or set()
    floor = 70 if deterministic_score >= 70 or "IMPERSONATION_SENSITIVE_REQUEST" in codes else 0
    if "IMPERSONATION_REQUEST" in codes:
        floor = max(floor, 50)
    return max(weighted, floor)


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
