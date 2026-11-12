from datetime import UTC, datetime

import pytest

from app.evaluation import policy_experiment as experiment
from app.schemas.analysis import DeterministicAssessment
from app.schemas.dataset import DatasetCase
from app.schemas.email import EmailIngestRequest
from app.services.deterministic_analysis import AnalysisContext


def make_case(case_id: str, label: str, split: str = "development") -> DatasetCase:
    return DatasetCase(
        case_id=case_id,
        split=split,
        label=label,
        expected_bec_type="OTHER" if label == "BEC" else None,
        email=EmailIngestRequest(
            message_id=f"<{case_id.lower()}@fixture.example>",
            sender_email="sender@fixture.example",
            subject="PRIVATE SUBJECT",
            body_text="PRIVATE BODY",
            received_at=datetime.now(UTC),
        ),
    )


def test_experimental_score_preserves_security_floor():
    candidate = experiment.PolicyCandidate(rules_weight=30, semantic_weight=70, alert_threshold=50)
    assert experiment.experimental_score(80, 0, candidate) == 70
    assert experiment.experimental_score(0, 80, candidate) == 56


def test_search_accepts_development_only_and_records_selection(monkeypatch):
    cases = [make_case("BEC_1", "BEC"), make_case("LEGIT_1", "LEGITIMATE")]

    def fake_detector(email, _context):
        return DeterministicAssessment(
            score=80 if email.message_id.startswith("<bec") else 0,
            signals=[],
            bec_type="OTHER" if email.message_id.startswith("<bec") else None,
        )

    monkeypatch.setattr(experiment, "assess_deterministically", fake_detector)
    report = experiment.run_policy_search(
        cases,
        AnalysisContext([], []),
        {"BEC_1": 80, "LEGIT_1": 80},
        config=experiment.PolicySearchConfig(rules_weights=(50,), alert_thresholds=(50,)),
        seed=17,
    )
    assert report.selected_trial_id == 0
    assert report.trials[0].metrics is not None
    assert report.trials[0].metrics.recall == 1
    assert report.trials[0].metrics.false_positive_rate == 0
    assert report.trials[0].seed == 17
    assert "PRIVATE BODY" not in report.model_dump_json()


def test_search_rejects_holdout_and_requires_trace_for_cached_outputs():
    cases = [make_case("HOLDOUT_1", "BEC", "holdout")]
    with pytest.raises(ValueError, match="development cases only"):
        experiment.run_policy_search(cases, AnalysisContext([], []), {"HOLDOUT_1": 80})

    development = [make_case("DEV_1", "BEC")]
    with pytest.raises(ValueError, match="provider, model, prompt and cache hash"):
        experiment.run_policy_search(
            development,
            AnalysisContext([], []),
            {"DEV_1": 80},
            semantic_source="cached_model_output",
        )


def test_hypothetical_scores_are_explicit_and_grid_is_small():
    cases = [make_case("DEV_1", "BEC"), make_case("HOLDOUT_1", "BEC", "holdout")]
    assert experiment.constant_semantic_scores(cases, 50) == {"DEV_1": 50}
    grid = experiment.candidate_grid(experiment.PolicySearchConfig())
    assert len(grid) == 25
    assert all(
        candidate.floor_policy_version == experiment.FLOOR_POLICY_VERSION for candidate in grid
    )
