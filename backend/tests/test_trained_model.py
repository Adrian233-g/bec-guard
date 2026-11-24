"""Inference from a pinned artifact never takes a path from email input."""

import hashlib
import json
from types import SimpleNamespace

import joblib
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from app.core.config import TrainedModelSettings
from app.services.trained_model import ModelPrediction, assisted_score, predict_email


def test_shadow_and_assist_never_lower_the_existing_detector_score():
    for score in (0, 40, 80):
        assert assisted_score(score, None) == score
        assert assisted_score(score, ModelPrediction("shadow", 0.99, 50, "a" * 64)) == score
        assert assisted_score(score, ModelPrediction("assist", 0.1, 0, "a" * 64)) == score
        assert assisted_score(score, ModelPrediction("assist", 0.99, 50, "a" * 64)) == max(
            score, 50
        )


def test_pinned_training_model_can_score_an_email_in_shadow_and_assist(tmp_path):
    model = make_pipeline(TfidfVectorizer(), LogisticRegression())
    model.fit(
        [
            "Pago urgente transferencia",
            "Cambia cuenta bancaria",
            "Informe de inventario",
            "Reunión",
        ],
        [1, 1, 0, 0],
    )
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report = tmp_path / "training_report.json"
    report.write_text(
        json.dumps({"status": "TECHNICAL_FIXTURE_ONLY", "selected": {"threshold": 0.5}}),
        encoding="utf-8",
    )
    email = SimpleNamespace(subject="Pago urgente", body_text="transferencia bancaria")

    settings = TrainedModelSettings(
        _env_file=None,
        bec_model_mode="shadow",
        bec_model_path=path,
        bec_model_sha256=digest,
        bec_model_report_path=report,
        bec_model_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
    )
    result = predict_email(email, settings)
    assert result.mode == "shadow" and result.sha256 == digest
    assert 0 <= result.probability <= 1
    assert result.score == 50

    settings.bec_model_mode = "assist"
    with pytest.raises(ValueError, match="qualifying authorized evaluation"):
        predict_email(email, settings)

    settings.bec_model_sha256 = "0" * 64
    settings.bec_model_mode = "shadow"
    with pytest.raises(ValueError, match="SHA-256"):
        predict_email(email, settings)
    assert (
        predict_email(email, TrainedModelSettings(_env_file=None, bec_model_mode="disabled"))
        is None
    )


def test_missing_artifact_or_training_report_fails_closed(tmp_path):
    settings = TrainedModelSettings(
        _env_file=None,
        bec_model_mode="assist",
        bec_model_path=tmp_path / "absent.joblib",
        bec_model_sha256="0" * 64,
        bec_model_report_path=tmp_path / "absent.json",
        bec_model_report_sha256="0" * 64,
    )
    with pytest.raises(OSError):
        predict_email(SimpleNamespace(subject="", body_text=""), settings)


def test_assist_requires_pinned_authorized_test_and_rejects_report_tampering(tmp_path):
    model = make_pipeline(TfidfVectorizer(), LogisticRegression())
    model.fit(["urgent wire", "pay now", "meeting", "inventory"], [1, 1, 0, 0])
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report_path = tmp_path / "report.json"
    report = {
        "status": "AUTHORIZED_TRAINING_VALIDATION",
        "test_status": "AUTHORIZED_TEST_EVALUATED",
        "test": {"tp": 20, "fn": 0, "fp": 5, "tn": 95},
        "selected": {"threshold": 0.5},
        "model_sha256": digest,
    }

    def settings_for(payload):
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return TrainedModelSettings(
            _env_file=None,
            bec_model_mode="assist",
            bec_model_path=path,
            bec_model_sha256=digest,
            bec_model_report_path=report_path,
            bec_model_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
        )

    email = SimpleNamespace(subject="urgent", body_text="wire")
    settings = settings_for(report)
    assert predict_email(email, settings).mode == "assist"
    report_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="report does not match"):
        predict_email(email, settings)
    for status, test in (
        ("PUBLIC_DIAGNOSTIC_TRAINING_ONLY", report["test"]),
        ("SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED", report["test"]),
        ("TECHNICAL_FIXTURE_ONLY", report["test"]),
        ("AUTHORIZED_TRAINING_VALIDATION", {"tp": 20, "fn": 0, "fp": 6, "tn": 94}),
        ("AUTHORIZED_TRAINING_VALIDATION", {"tp": 19, "fn": 0, "fp": 0, "tn": 100}),
    ):
        settings = settings_for({**report, "status": status, "test": test})
        with pytest.raises(ValueError, match="qualifying authorized evaluation"):
            predict_email(email, settings)
    settings = settings_for({**report, "model_sha256": "0" * 64})
    with pytest.raises(ValueError, match="qualifying authorized evaluation"):
        predict_email(email, settings)
    settings = settings_for(
        {
            **report,
            "status": "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED",
            "test_status": "SEALED_NOT_EVALUATED",
        }
    )
    settings.bec_model_mode = "shadow"
    assert predict_email(email, settings).mode == "shadow"
