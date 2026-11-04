from types import SimpleNamespace

import pytest

from app.scripts.check_development import load_synthetic_context
from app.scripts.compare_score_policies import candidate_score, compare


@pytest.mark.parametrize("rules,semantic,expected", [(0, 100, 70), (52, 40, 44), (70, 0, 70)])
def test_candidate_score_and_existing_rules_floor(rules, semantic, expected):
    assert candidate_score(rules, semantic) == expected


@pytest.mark.parametrize("invalid", [-1, 101, True, 1.2])
def test_candidate_rejects_invalid_scores(invalid):
    with pytest.raises(ValueError):
        candidate_score(invalid, 20)


def test_holdout_not_read_and_iterator_is_safe():
    class Reserved:
        split = "holdout"

        def __getattr__(self, name):
            raise AssertionError(f"Holdout accessed: {name}")

    result = compare(iter([Reserved()]), load_synthetic_context(), (20, 80))
    assert list(result) == ["20", "80"]
    assert all(not counts for policy in result.values() for counts in policy.values())


def test_raising_semantic_score_can_trigger_legitimate_alert():
    from datetime import UTC, datetime

    from app.schemas.dataset import DatasetLabel
    from app.schemas.email import EmailIngestRequest

    case = SimpleNamespace(
        split="development",
        label=DatasetLabel.LEGITIMATE,
        email=EmailIngestRequest(
            message_id="simulation",
            sender_email="colleague@example.org",
            subject="Agenda",
            body_text="Nos vemos mañana.",
            received_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    result = compare([case], load_synthetic_context(), (20, 80))
    assert result["20"]["both"]["LEGITIMATE_alerts"] == 0
    assert result["80"]["both"]["LEGITIMATE_alerts"] == 1
    assert result["80"]["baseline_50_50_70"]["LEGITIMATE_alerts"] == 0
