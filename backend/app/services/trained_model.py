"""Pinned offline classifier inference; a model is loaded only from a trusted local file."""

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal, NamedTuple

from app.core.config import TrainedModelSettings
from app.services.alerts import ALERT_THRESHOLD


class ModelPrediction(NamedTuple):
    mode: Literal["shadow", "assist"]
    probability: float
    score: int
    sha256: str


def _assist_is_eligible(report: dict, model_sha256: str) -> bool:
    """Technical promotion gate; its input is a hash-pinned, trusted local report."""
    if (
        report.get("status") != "AUTHORIZED_TRAINING_VALIDATION"
        or report.get("test_status") != "AUTHORIZED_TEST_EVALUATED"
        or report.get("model_sha256") != model_sha256
    ):
        return False
    test = report.get("test")
    if not isinstance(test, dict) or any(
        type(test.get(key)) is not int or test[key] < 0 for key in ("tp", "fn", "fp", "tn")
    ):
        return False
    positives, negatives = test["tp"] + test["fn"], test["fp"] + test["tn"]
    return (
        positives >= 20
        and negatives >= 100
        and test["tp"] / positives >= 0.6
        and test["fp"] / negatives <= 0.05
    )


def assisted_score(base_score: int, prediction: ModelPrediction | None) -> int:
    """Keep the existing detector score unless assist positively classifies the email."""
    if prediction is not None and prediction.mode == "assist":
        return max(base_score, prediction.score)
    return base_score


@lru_cache(maxsize=2)
def _load_model(path: Path, sha256: str):
    # joblib is pickle-based. Never load uploads or a file whose hash does not match
    # the locally configured, explicitly approved artifact.
    import joblib

    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise ValueError("Configured model artifact is missing or does not match its SHA-256")
    model = joblib.load(path)
    if not callable(getattr(model, "predict_proba", None)):
        raise ValueError("Configured model does not support probability inference")
    return model


def predict_email(email, settings: TrainedModelSettings | None = None) -> ModelPrediction | None:
    if settings is None:
        settings = TrainedModelSettings()
    mode = settings.bec_model_mode
    if mode == "disabled":
        return None
    if not settings.bec_model_path or not settings.bec_model_sha256:
        raise ValueError("BEC model mode requires a local path and SHA-256")
    if settings.bec_model_report_path is None or not settings.bec_model_report_sha256:
        raise ValueError("BEC model mode requires a SHA-256-pinned training report")
    report_bytes = settings.bec_model_report_path.read_bytes()
    if hashlib.sha256(report_bytes).hexdigest() != settings.bec_model_report_sha256:
        raise ValueError("Configured training report does not match its SHA-256")
    report = json.loads(report_bytes)
    if report.get("status") not in {
        "TECHNICAL_FIXTURE_ONLY",
        "PUBLIC_DIAGNOSTIC_TRAINING_ONLY",
        "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED",
        "AUTHORIZED_TRAINING_VALIDATION",
    }:
        raise ValueError("Configured training report is not eligible for inference")
    if mode == "assist" and not _assist_is_eligible(report, settings.bec_model_sha256):
        raise ValueError("Assist requires a qualifying authorized evaluation")
    threshold = report.get("selected", {}).get("threshold")
    if type(threshold) not in (float, int) or not 0 < threshold < 1:
        raise ValueError("Configured training report has no valid frozen threshold")
    path = settings.bec_model_path.resolve()
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != settings.bec_model_sha256
    ):
        raise ValueError("Configured model artifact is missing or does not match its SHA-256")
    if report.get("model_sha256", settings.bec_model_sha256) != settings.bec_model_sha256:
        raise ValueError("Configured model and training report do not match")
    model = _load_model(path, settings.bec_model_sha256)
    if list(model.classes_) != [0, 1]:
        raise ValueError("Configured model has unexpected class labels")
    probability = float(model.predict_proba([f"{email.subject}\n{email.body_text}"])[0][1])
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("Model returned an invalid probability")
    # An affirmative classification can raise the ordinal operational score to
    # the existing alert threshold; raw probabilities are NOT ordinal risk scores.
    return ModelPrediction(
        mode,
        probability,
        ALERT_THRESHOLD if probability >= threshold else 0,
        settings.bec_model_sha256,
    )
