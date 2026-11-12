"""Direct, defined-denominator metrics; ERROR predictions never become negatives."""

from collections.abc import Iterable
from math import ceil
from statistics import mean, median

from app.evaluation.contracts import (
    BinaryMetrics,
    CasePrediction,
    CurveMetrics,
    CurvePoint,
    HardNegativeMetrics,
    LatencyMetrics,
    TypeMetrics,
)
from app.models.enums import BECType


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _status_cases(
    cases: Iterable[CasePrediction], statuses: tuple[str, ...]
) -> list[CasePrediction]:
    return [case for case in cases if case.status in statuses]


def binary_metrics(
    cases: list[CasePrediction], *, alert: bool = False, statuses: tuple[str, ...] = ("COMPLETED",)
) -> BinaryMetrics:
    tp = tn = fp = fn = 0
    selected = _status_cases(cases, statuses)
    for case in selected:
        positive = case.predicted_positive_alert if alert else case.predicted_positive_detection
        actual = case.ground_truth == "BEC"
        tp += int(actual and positive is True)
        tn += int(not actual and positive is False)
        fp += int(not actual and positive is True)
        fn += int(actual and positive is False)
    return BinaryMetrics(
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        precision=ratio(tp, tp + fp),
        recall=ratio(tp, tp + fn),
        f1=ratio(2 * tp, 2 * tp + fp + fn),
        accuracy=ratio(tp + tn, tp + tn + fp + fn),
        specificity=ratio(tn, tn + fp),
        false_positive_rate=ratio(fp, fp + tn),
        effective_recall=ratio(tp, sum(c.ground_truth == "BEC" for c in cases)),
    )


def hard_negative_metrics(cases: list[CasePrediction]) -> HardNegativeMetrics:
    hard = [c for c in cases if c.is_hard_negative]
    completed = [c for c in hard if c.status == "COMPLETED"]
    fallback = [c for c in hard if c.status == "FALLBACK"]
    scored = completed + fallback
    detection = sum(c.predicted_positive_detection is True for c in scored)
    alert = sum(c.predicted_positive_alert is True for c in scored)
    return HardNegativeMetrics(
        total=len(hard),
        completed=len(completed),
        fallback=len(fallback),
        errors=len(hard) - len(scored),
        false_positives_detection=detection,
        false_positives_alert=alert,
        fallback_false_positives_detection=sum(
            c.predicted_positive_detection is True for c in fallback
        ),
        fallback_false_positives_alert=sum(c.predicted_positive_alert is True for c in fallback),
        fpr_detection=ratio(detection, len(scored)),
        fpr_alert=ratio(alert, len(scored)),
    )


def type_metrics(
    cases: list[CasePrediction], *, statuses: tuple[str, ...] | None = None
) -> TypeMetrics:
    selected = cases if statuses is None else _status_cases(cases, statuses)
    attacks = [c for c in selected if c.ground_truth == "BEC"]
    breakdown = {}
    for kind in BECType:
        group = [c for c in attacks if c.expected_bec_type == kind]
        correct = sum(c.predicted_bec_type == kind for c in group)
        missing = sum(c.predicted_bec_type is None for c in group)
        breakdown[kind.value] = {
            "total": len(group),
            "correct": correct,
            "incorrect": len(group) - correct - missing,
            "unclassified": missing,
            "errors": sum(c.status == "ERROR" for c in group),
        }
    correct = sum(v["correct"] for v in breakdown.values())
    return TypeMetrics(
        total_bec=len(attacks),
        correct=correct,
        accuracy=ratio(correct, len(attacks)),
        breakdown=breakdown,
    )


def latency_metrics(
    cases: list[CasePrediction], *, statuses: tuple[str, ...] | None = None
) -> LatencyMetrics:
    selected = cases if statuses is None else _status_cases(cases, statuses)
    values = sorted(c.elapsed_ms for c in selected)
    return LatencyMetrics(
        mean_ms=mean(values) if values else None,
        median_ms=median(values) if values else None,
        p95_ms=values[ceil(0.95 * len(values)) - 1] if values else None,
    )


def _auc(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    return sum(
        (x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False)
    )


def curve_metrics(
    cases: list[CasePrediction], *, statuses: tuple[str, ...] = ("COMPLETED",)
) -> CurveMetrics | None:
    """Build curves from individual valid scores, never from aggregate counts."""
    selected = _status_cases(cases, statuses)
    if not selected or any(case.score is None for case in selected):
        return None
    positives = sum(case.ground_truth == "BEC" for case in selected)
    negatives = len(selected) - positives
    if not positives or not negatives:
        return None

    roc: list[CurvePoint] = []
    for threshold in range(101, -1, -1):
        tp = tn = fp = fn = 0
        for case in selected:
            predicted = case.score >= threshold
            actual = case.ground_truth == "BEC"
            tp += int(actual and predicted)
            tn += int(not actual and not predicted)
            fp += int(not actual and predicted)
            fn += int(actual and not predicted)
        roc.append(
            CurvePoint(
                threshold=threshold,
                tp=tp,
                tn=tn,
                fp=fp,
                fn=fn,
                false_positive_rate=ratio(fp, fp + tn),
                true_positive_rate=ratio(tp, tp + fn),
                precision=ratio(tp, tp + fp),
                recall=ratio(tp, tp + fn),
            )
        )
    roc_auc = _auc(
        [(point.false_positive_rate or 0, point.true_positive_rate or 0) for point in roc]
    )
    pr_auc = _auc([(point.recall or 0, point.precision or 0) for point in roc])
    return CurveMetrics(
        cases=len(selected),
        positives=positives,
        negatives=negatives,
        roc_auc=roc_auc,
        pr_auc=pr_auc,
        roc=roc,
        precision_recall=roc,
    )
