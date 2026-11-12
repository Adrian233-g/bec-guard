from collections.abc import Callable, Iterable
from time import perf_counter

from pydantic import ValidationError

from app.evaluation.contracts import (
    DETECTION_THRESHOLD,
    CasePrediction,
    EvaluationMetadata,
    EvaluationResult,
)
from app.evaluation.metrics import (
    binary_metrics,
    curve_metrics,
    hard_negative_metrics,
    latency_metrics,
    ratio,
    type_metrics,
)
from app.schemas.dataset import DatasetCase
from app.services.alerts import ALERT_THRESHOLD
from app.services.deterministic_analysis import AnalysisContext, assess_deterministically
from app.services.email_analysis import create_semantic_analyzer
from app.services.hybrid_scoring import combine_scores, resolve_bec_type
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalysisError, SemanticAnalyzer


def evaluate(
    cases: Iterable[DatasetCase],
    context: AnalysisContext,
    metadata: EvaluationMetadata,
    *,
    allow_external_llm: bool = False,
    analyzer_factory: Callable[[], SemanticAnalyzer] = create_semantic_analyzer,
    detector: Callable = assess_deterministically,
    clock: Callable[[], float] = perf_counter,
) -> EvaluationResult:
    if metadata.mode == "hybrid" and not allow_external_llm:
        raise ValueError("Hybrid mode requires explicit external LLM consent")
    if metadata.thresholds != {"detection": DETECTION_THRESHOLD, "alert": ALERT_THRESHOLD}:
        raise ValueError("Evaluation thresholds must match the frozen policies")
    predictions = []
    for case in cases:
        if case.split.value != metadata.split:
            continue
        start = clock()
        # Only normalized email and context cross the detector boundary.
        det = detector(case.email, context)
        score, kind, error = det.score, det.bec_type, None
        status = "COMPLETED"
        if metadata.mode == "fallback":
            status = "FALLBACK"
            error = LLMErrorCode.NOT_CONFIGURED.value
        if metadata.mode == "hybrid":
            try:
                semantic = analyzer_factory().assess(case.email, det, context)
                score = combine_scores(
                    det.score, semantic.risk_score, signal_codes={s.code for s in det.signals}
                )
                kind = resolve_bec_type(score, det, semantic)
            except ValidationError:
                score, kind = det.score, det.bec_type
                error = LLMErrorCode.NOT_CONFIGURED.value
                status = "FALLBACK"
            except SemanticAnalysisError as failure:
                score, kind = det.score, det.bec_type
                error = failure.code.value
                status = "FALLBACK"
        elapsed = max(0.0, (clock() - start) * 1000)
        # Annotation access occurs only after prediction (never input features).
        predictions.append(
            CasePrediction(
                case_id=case.case_id,
                ground_truth=case.label,
                expected_bec_type=case.expected_bec_type,
                predicted_positive_detection=None
                if score is None
                else score >= DETECTION_THRESHOLD,
                predicted_positive_alert=None if score is None else score >= ALERT_THRESHOLD,
                score=score,
                predicted_bec_type=kind,
                status=status,
                error_code=error,
                elapsed_ms=elapsed,
                is_hard_negative=case.is_hard_negative,
            )
        )
    completed = sum(c.status == "COMPLETED" for c in predictions)
    fallback = sum(c.status == "FALLBACK" for c in predictions)
    errors = sum(c.status == "ERROR" for c in predictions)
    scored_statuses = ("COMPLETED", "FALLBACK")
    return EvaluationResult(
        **metadata.model_dump(),
        cases_total=len(predictions),
        completed=completed,
        fallback=fallback,
        errors=errors,
        coverage=ratio(completed + fallback, len(predictions)),
        completed_coverage=ratio(completed, len(predictions)),
        fallback_rate=ratio(fallback, len(predictions)),
        error_rate=ratio(errors, len(predictions)),
        detection_metrics=binary_metrics(predictions, statuses=scored_statuses),
        alert_metrics=binary_metrics(predictions, alert=True, statuses=scored_statuses),
        completed_detection_metrics=binary_metrics(predictions),
        completed_alert_metrics=binary_metrics(predictions, alert=True),
        fallback_detection_metrics=binary_metrics(predictions, statuses=("FALLBACK",)),
        fallback_alert_metrics=binary_metrics(predictions, alert=True, statuses=("FALLBACK",)),
        hard_negatives=hard_negative_metrics(predictions),
        bec_types=type_metrics(predictions),
        completed_bec_types=type_metrics(predictions, statuses=("COMPLETED",)),
        fallback_bec_types=type_metrics(predictions, statuses=("FALLBACK",)),
        latency=latency_metrics(predictions),
        completed_latency=latency_metrics(predictions, statuses=("COMPLETED",)),
        fallback_latency=latency_metrics(predictions, statuses=("FALLBACK",)),
        curves=curve_metrics(predictions, statuses=scored_statuses) if errors == 0 else None,
        completed_curves=curve_metrics(predictions),
        fallback_curves=curve_metrics(predictions, statuses=("FALLBACK",)),
        cases=predictions,
    )
