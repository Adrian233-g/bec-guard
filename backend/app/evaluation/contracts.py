from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import BECType
from app.schemas.analysis import Score
from app.schemas.dataset import DatasetLabel

EVALUATION_VERSION = "eval-v2"
DETECTION_THRESHOLD = 40


class BinaryMetrics(BaseModel):
    tp: int
    tn: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    accuracy: float | None
    specificity: float | None
    false_positive_rate: float | None
    effective_recall: float | None


class EvaluationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_version: Literal["eval-v2"] = EVALUATION_VERSION
    mode: Literal["deterministic", "hybrid", "fallback"]
    generated_at: AwareDatetime
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: Literal["holdout", "evaluation"] = "holdout"
    policies: dict[str, str]
    thresholds: dict[str, int]
    detector_sha256: dict[str, str]
    provider: str | None = None
    model: str | None = None


class CasePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    ground_truth: DatasetLabel
    expected_bec_type: BECType | None
    predicted_positive_detection: bool | None
    predicted_positive_alert: bool | None
    score: Score | None
    predicted_bec_type: BECType | None
    status: Literal["COMPLETED", "FALLBACK", "ERROR"]
    error_code: str | None = None
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    is_hard_negative: bool


class HardNegativeMetrics(BaseModel):
    total: int
    completed: int
    fallback: int
    errors: int
    false_positives_detection: int
    false_positives_alert: int
    fallback_false_positives_detection: int
    fallback_false_positives_alert: int
    fpr_detection: float | None
    fpr_alert: float | None


class TypeMetrics(BaseModel):
    total_bec: int
    correct: int
    accuracy: float | None
    breakdown: dict[str, dict[str, int]]


class LatencyMetrics(BaseModel):
    mean_ms: float | None
    median_ms: float | None
    p95_ms: float | None


class CurvePoint(BaseModel):
    threshold: int
    tp: int
    tn: int
    fp: int
    fn: int
    false_positive_rate: float | None
    true_positive_rate: float | None
    precision: float | None
    recall: float | None


class CurveMetrics(BaseModel):
    cases: int
    positives: int
    negatives: int
    roc_auc: float | None
    pr_auc: float | None
    roc: list[CurvePoint]
    precision_recall: list[CurvePoint]


class EvaluationResult(EvaluationMetadata):
    cases_total: int
    completed: int
    fallback: int
    errors: int
    coverage: float | None
    completed_coverage: float | None
    fallback_rate: float | None
    error_rate: float | None
    detection_metrics: BinaryMetrics
    alert_metrics: BinaryMetrics
    completed_detection_metrics: BinaryMetrics
    completed_alert_metrics: BinaryMetrics
    fallback_detection_metrics: BinaryMetrics
    fallback_alert_metrics: BinaryMetrics
    hard_negatives: HardNegativeMetrics
    bec_types: TypeMetrics
    completed_bec_types: TypeMetrics
    fallback_bec_types: TypeMetrics
    latency: LatencyMetrics
    completed_latency: LatencyMetrics
    fallback_latency: LatencyMetrics
    curves: CurveMetrics | None
    completed_curves: CurveMetrics | None
    fallback_curves: CurveMetrics | None
    cases: list[CasePrediction]
