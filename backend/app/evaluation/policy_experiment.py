"""Development-only policy search; never imported by production code.

This module evaluates arithmetic policy candidates against deterministic evidence and
caller-supplied semantic scores. It deliberately has no provider, database, Optuna,
or policy mutation dependency. A semantic score may be hypothetical or a previously
captured model output with provenance supplied by the caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.dataset import DatasetCase, DatasetLabel, DatasetSplit
from app.services.deterministic_analysis import AnalysisContext, assess_deterministically

EXPERIMENT_VERSION = "policy-search-v1"
DEFAULT_RULE_WEIGHTS = (30, 40, 50, 60, 70)
DEFAULT_ALERT_THRESHOLDS = (50, 55, 60, 65, 70)
DEFAULT_MAX_FALSE_POSITIVE_RATE = 0.05
DEFAULT_MIN_COVERAGE = 0.95
FLOOR_POLICY_VERSION = "hybrid-v2-security-floors"


class PolicyCandidate(BaseModel):
    """Candidate knobs; security floors intentionally are not search parameters."""

    model_config = ConfigDict(extra="forbid")

    rules_weight: int = Field(ge=0, le=100)
    semantic_weight: int = Field(ge=0, le=100)
    alert_threshold: int = Field(ge=40, le=85)
    floor_deterministic_threshold: int = Field(default=70, ge=0, le=100)
    floor_score: int = Field(default=70, ge=0, le=100)
    floor_policy_version: str = FLOOR_POLICY_VERSION

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> PolicyCandidate:
        if self.rules_weight + self.semantic_weight != 100:
            raise ValueError("Policy weights must sum to 100")
        return self


class PolicySearchConfig(BaseModel):
    """Pre-declared search space and acceptance constraints."""

    model_config = ConfigDict(extra="forbid")

    rules_weights: tuple[int, ...] = DEFAULT_RULE_WEIGHTS
    alert_thresholds: tuple[int, ...] = DEFAULT_ALERT_THRESHOLDS
    max_false_positive_rate: float = Field(default=DEFAULT_MAX_FALSE_POSITIVE_RATE, ge=0, le=1)
    min_coverage: float = Field(default=DEFAULT_MIN_COVERAGE, ge=0, le=1)

    @model_validator(mode="after")
    def validate_space(self) -> PolicySearchConfig:
        if not self.rules_weights or not self.alert_thresholds:
            raise ValueError("Search space cannot be empty")
        if any(type(weight) is not int or not 0 <= weight <= 100 for weight in self.rules_weights):
            raise ValueError("Rule weights must be integers between 0 and 100")
        if any(
            type(threshold) is not int or not 40 <= threshold <= 85
            for threshold in self.alert_thresholds
        ):
            raise ValueError("Alert thresholds must be integers between 40 and 85")
        return self


class TrialMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases_total: int = Field(ge=0)
    scored: int = Field(ge=0)
    coverage: float | None
    tp: int = Field(ge=0)
    tn: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    recall: float | None
    false_positive_rate: float | None
    precision: float | None
    alerts: int = Field(ge=0)
    hard_negative_total: int = Field(ge=0)
    hard_negative_false_positives: int = Field(ge=0)


class TrialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trial_id: int = Field(ge=0)
    status: Literal["COMPLETED", "FAILED"]
    candidate: PolicyCandidate
    objective: float | None
    feasible: bool | None
    constraints: dict[str, bool]
    metrics: TrialMetrics | None
    seed: int
    duration_ms: float = Field(ge=0)
    semantic_source: Literal["hypothetical", "cached_model_output"]
    semantic_provider: str | None = None
    semantic_model: str | None = None
    semantic_prompt_version: str | None = None
    semantic_cache_sha256: str | None = None
    estimated_external_calls: int = Field(ge=0)
    failure_reason: str | None = None


class PolicyExperimentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_version: Literal["policy-search-v1"] = EXPERIMENT_VERSION
    generated_at: datetime
    split: Literal["development"] = "development"
    objective_definition: str
    selection_rule: str
    search_config: PolicySearchConfig
    seed: int
    semantic_source: Literal["hypothetical", "cached_model_output"]
    semantic_provider: str | None = None
    semantic_model: str | None = None
    semantic_prompt_version: str | None = None
    semantic_cache_sha256: str | None = None
    estimated_external_calls: int = Field(ge=0)
    selected_trial_id: int | None
    trials: list[TrialRecord]


OBJECTIVE_DEFINITION = (
    "maximize recall - 0.25*false_positive_rate - 0.10*(1-coverage), "
    "subject to false_positive_rate <= 0.05 and coverage >= 0.95"
)
SELECTION_RULE = (
    "select feasible trial by objective descending, then recall descending, "
    "false_positive_rate ascending, alert threshold ascending"
)


def experimental_score(
    deterministic_score: int,
    semantic_score: int,
    candidate: PolicyCandidate,
    *,
    signal_codes: set[str] | None = None,
) -> int:
    """Apply candidate weights while retaining production security floors."""
    if any(
        type(score) is not int or not 0 <= score <= 100
        for score in (deterministic_score, semantic_score)
    ):
        raise ValueError("Scores must be integers between 0 and 100")
    weighted = (
        candidate.rules_weight * deterministic_score
        + candidate.semantic_weight * semantic_score
        + 50
    ) // 100
    floor = (
        candidate.floor_score
        if deterministic_score >= candidate.floor_deterministic_threshold
        else 0
    )
    codes = signal_codes or set()
    if "IMPERSONATION_SENSITIVE_REQUEST" in codes:
        floor = max(floor, 70)
    if "IMPERSONATION_REQUEST" in codes:
        floor = max(floor, 50)
    return max(weighted, floor)


def candidate_grid(config: PolicySearchConfig) -> list[PolicyCandidate]:
    return [
        PolicyCandidate(
            rules_weight=rules_weight,
            semantic_weight=100 - rules_weight,
            alert_threshold=threshold,
        )
        for rules_weight in config.rules_weights
        for threshold in config.alert_thresholds
    ]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _score_metrics(
    cases: Sequence[DatasetCase],
    scores: Mapping[str, int],
    candidate: PolicyCandidate,
    context: AnalysisContext,
) -> TrialMetrics:
    if not cases:
        raise ValueError("Development set is empty")
    tp = tn = fp = fn = alerts = hard_total = hard_fp = 0
    for case in cases:
        semantic = scores[case.case_id]
        deterministic = assess_deterministically(case.email, context)
        score = experimental_score(
            deterministic.score,
            semantic,
            candidate,
            signal_codes={signal.code for signal in deterministic.signals},
        )
        alert = score >= candidate.alert_threshold
        alerts += int(alert)
        if case.label == DatasetLabel.BEC:
            tp += int(alert)
            fn += int(not alert)
        else:
            tn += int(not alert)
            fp += int(alert)
            if case.is_hard_negative:
                hard_total += 1
                hard_fp += int(alert)
    negatives = tn + fp
    positives = tp + fn
    return TrialMetrics(
        cases_total=len(cases),
        scored=len(cases),
        coverage=1.0,
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        recall=_ratio(tp, positives),
        false_positive_rate=_ratio(fp, negatives),
        precision=_ratio(tp, tp + fp),
        alerts=alerts,
        hard_negative_total=hard_total,
        hard_negative_false_positives=hard_fp,
    )


def _objective(metrics: TrialMetrics) -> float:
    return (
        (metrics.recall or 0.0)
        - 0.25 * (metrics.false_positive_rate or 0.0)
        - 0.10 * (1 - (metrics.coverage or 0.0))
    )


def run_policy_search(
    cases: Sequence[DatasetCase],
    context: AnalysisContext,
    semantic_scores: Mapping[str, int],
    *,
    config: PolicySearchConfig | None = None,
    seed: int = 0,
    semantic_source: Literal["hypothetical", "cached_model_output"] = "hypothetical",
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_prompt_version: str | None = None,
    semantic_cache_sha256: str | None = None,
    estimated_external_calls: int = 0,
) -> PolicyExperimentReport:
    """Run an explicit development-only search and return a serializable report."""
    development = list(cases)
    if not development:
        raise ValueError("Development set is empty")
    if any(case.split != DatasetSplit.DEVELOPMENT for case in development):
        raise ValueError("Policy search accepts development cases only")
    case_ids = {case.case_id for case in development}
    missing = case_ids - semantic_scores.keys()
    extra = semantic_scores.keys() - case_ids
    if missing or extra:
        raise ValueError("Semantic score cache must match development case IDs exactly")
    if semantic_source == "cached_model_output" and not all(
        (semantic_provider, semantic_model, semantic_prompt_version, semantic_cache_sha256)
    ):
        raise ValueError("Cached model outputs require provider, model, prompt and cache hash")
    if type(estimated_external_calls) is not int or estimated_external_calls < 0:
        raise ValueError("Estimated external calls must be a non-negative integer")
    search_config = config or PolicySearchConfig()
    trials: list[TrialRecord] = []
    for trial_id, candidate in enumerate(candidate_grid(search_config)):
        started = perf_counter()
        try:
            metrics = _score_metrics(development, semantic_scores, candidate, context)
            fpr_ok = (metrics.false_positive_rate or 0.0) <= search_config.max_false_positive_rate
            coverage_ok = (metrics.coverage or 0.0) >= search_config.min_coverage
            feasible = fpr_ok and coverage_ok
            trials.append(
                TrialRecord(
                    trial_id=trial_id,
                    status="COMPLETED",
                    candidate=candidate,
                    objective=_objective(metrics),
                    feasible=feasible,
                    constraints={"false_positive_rate": fpr_ok, "coverage": coverage_ok},
                    metrics=metrics,
                    seed=seed,
                    duration_ms=max(0.0, (perf_counter() - started) * 1000),
                    semantic_source=semantic_source,
                    semantic_provider=semantic_provider,
                    semantic_model=semantic_model,
                    semantic_prompt_version=semantic_prompt_version,
                    semantic_cache_sha256=semantic_cache_sha256,
                    estimated_external_calls=estimated_external_calls,
                )
            )
        except Exception as error:  # Record a failed trial without hiding process interrupts.
            trials.append(
                TrialRecord(
                    trial_id=trial_id,
                    status="FAILED",
                    candidate=candidate,
                    objective=None,
                    feasible=None,
                    constraints={},
                    metrics=None,
                    seed=seed,
                    duration_ms=max(0.0, (perf_counter() - started) * 1000),
                    semantic_source=semantic_source,
                    semantic_provider=semantic_provider,
                    semantic_model=semantic_model,
                    semantic_prompt_version=semantic_prompt_version,
                    semantic_cache_sha256=semantic_cache_sha256,
                    estimated_external_calls=estimated_external_calls,
                    failure_reason=str(error),
                )
            )
    feasible_trials = [trial for trial in trials if trial.status == "COMPLETED" and trial.feasible]
    selected = max(
        feasible_trials,
        key=lambda trial: (
            trial.objective if trial.objective is not None else float("-inf"),
            trial.metrics.recall if trial.metrics and trial.metrics.recall is not None else -1,
            -(
                trial.metrics.false_positive_rate
                if trial.metrics and trial.metrics.false_positive_rate is not None
                else 1
            ),
            -trial.candidate.alert_threshold,
        ),
        default=None,
    )
    return PolicyExperimentReport(
        generated_at=datetime.now(UTC),
        objective_definition=OBJECTIVE_DEFINITION,
        selection_rule=SELECTION_RULE,
        search_config=search_config,
        seed=seed,
        semantic_source=semantic_source,
        semantic_provider=semantic_provider,
        semantic_model=semantic_model,
        semantic_prompt_version=semantic_prompt_version,
        semantic_cache_sha256=semantic_cache_sha256,
        estimated_external_calls=estimated_external_calls,
        selected_trial_id=selected.trial_id if selected else None,
        trials=trials,
    )


def constant_semantic_scores(cases: Sequence[DatasetCase], score: int) -> dict[str, int]:
    """Build a clearly hypothetical scenario for arithmetic comparison only."""
    if type(score) is not int or not 0 <= score <= 100:
        raise ValueError("Hypothetical semantic score must be an integer between 0 and 100")
    return {case.case_id: score for case in cases if case.split == DatasetSplit.DEVELOPMENT}
