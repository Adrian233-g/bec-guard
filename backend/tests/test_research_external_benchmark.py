"""External benchmark must respect publisher labels and preserve denominators."""

import csv

import numpy as np
import pytest

from research.bec_training.external_benchmark import SOURCE, _load, _score


def test_external_csv_uses_only_ham_and_deduplicates_exact_messages(tmp_path, monkeypatch):
    monkeypatch.setitem(SOURCE, "enron", {"expected": {"0": 3, "1": 1}, "label": "label"})
    path = tmp_path / "enron.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["subject", "body", "label"])
        writer.writerows(
            [
                ["Invoice", "Please pay", "0"],
                [" invoice ", "please   pay", "0"],
                ["", "", "0"],
                ["Urgent", "Phishing", "1"],
            ]
        )
    texts, summary = _load(path, "enron")
    assert texts == ["Invoice\nPlease pay"]
    assert summary["source_rows"] == 4
    assert summary["excluded_exact_duplicates"] == 1
    assert summary["excluded_empty"] == 1
    assert summary["evaluated"] == 1


def test_external_csv_rejects_changed_label_distribution(tmp_path, monkeypatch):
    monkeypatch.setitem(SOURCE, "bec2", {"expected": {"positive": 2}, "label": "Human"})
    path = tmp_path / "bec2.csv"
    path.write_text("subject,body,Human\nA,B,positive\n", encoding="utf-8")
    with pytest.raises(ValueError, match="label distribution"):
        _load(path, "bec2")


def test_external_scores_have_correct_positive_and_negative_denominators():
    class Model:
        def predict_proba(self, texts):
            return np.array([[1 - p, p] for p in (0.9 if "BEC" in t else 0.1 for t in texts)])

    assert _score(Model(), ["BEC", "ham"], 0.5, positive=True) == {
        "tp": 1,
        "fn": 1,
        "recall": 0.5,
    }
    assert _score(Model(), ["BEC", "ham"], 0.5, positive=False) == {
        "fp": 1,
        "tn": 1,
        "fpr": 0.5,
    }
