"""Public-label training remains exploratory and separates selection from testing."""

import json

import numpy as np
import pytest

from research.bec_training.create_training_dataset import create_training_dataset
from research.bec_training.data import load_research_jsonl, split_manifest
from research.bec_training.public_retraining import (
    partition_ham,
    select_threshold,
    train_public_candidate,
)


def test_public_ham_partition_is_repeatable_and_disjoint():
    inputs = [f"Subject {i}\nMessage number {i}" for i in range(200)]
    first = partition_ham(inputs)
    assert first == partition_ham(list(reversed(inputs)))
    train, validation = first
    assert train and validation and not set(train) & set(validation)
    assert len(train) + len(validation) == len(inputs)


def test_threshold_selection_rejects_false_positive_rate_above_five_percent():
    class Model:
        def predict_proba(self, texts):
            values = {"positive": 0.7, "negative-high": 0.55, "negative": 0.1}
            return np.array([[1 - values[text], values[text]] for text in texts])

    threshold, choices = select_threshold(
        Model(), ["positive"] * 20, ["negative-high"] + ["negative"] * 19
    )
    assert choices["0.5"]["fpr"] == 0.05
    assert threshold == 0.5
    threshold, choices = select_threshold(
        Model(), ["positive"] * 20, ["negative-high"] * 2 + ["negative"] * 18
    )
    assert choices["0.5"]["fpr"] == 0.1
    assert threshold == 0.6
    assert choices["0.6"]["recall"] == 1.0


def test_public_training_rejects_a_changed_synthetic_split_before_reading_public_mail(tmp_path):
    corpus_dir = tmp_path / "corpus"
    create_training_dataset(corpus_dir)
    dataset = corpus_dir / "dataset.jsonl"
    split = split_manifest(dataset, load_research_jsonl(dataset))
    split["seed"] += 1
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps(split), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen splitting rule"):
        train_public_candidate(
            dataset,
            split_path,
            tmp_path / "absent.csv",
            tmp_path / "absent2.csv",
            tmp_path / "absent3.csv",
        )
