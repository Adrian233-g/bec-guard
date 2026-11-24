"""The article exporter checks real frozen artifacts instead of trusting copied tables."""

import hashlib
import json
from pathlib import Path

import pytest

from research.bec_training.article_evidence import build_evidence
from research.bec_training.create_training_dataset import create_training_dataset
from research.bec_training.data import ResearchDataError, load_research_jsonl, split_manifest
from research.bec_training.train_dataset import train_dataset


def test_evidence_is_aggregated_and_tampered_provenance_is_rejected(tmp_path):
    corpus_dir = tmp_path / "training"
    create_training_dataset(corpus_dir)
    dataset = corpus_dir / "dataset.jsonl"
    manifest = split_manifest(dataset, load_research_jsonl(dataset))
    (corpus_dir / "split_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    training_report = train_dataset(dataset, corpus_dir / "model", evaluate_test=True)
    assert (
        training_report["model_sha256"]
        == hashlib.sha256((corpus_dir / "model" / "model.joblib").read_bytes()).hexdigest()
    )
    context = Path(__file__).resolve().parents[2] / "datasets" / "context.json"

    evidence = build_evidence(corpus_dir, context)
    assert evidence["status"] == "SYNTHETIC_FIXTURE_REUSE_DESCRIPTIVE_ONLY"
    assert evidence["real_world_validity"] == "NOT_ESTABLISHED"
    assert sum(evidence["labels"].values()) == 500
    assert evidence["test_results"]["trained_model"]["total"] == 74
    assert all(
        sum(result[key] for key in ("tp", "fp", "tn", "fn")) == 74
        for result in evidence["test_results"].values()
    )
    serialized = json.dumps(evidence)
    assert "body_text" not in serialized and "sender_email" not in serialized

    path = corpus_dir / "manifest.json"
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["dataset_sha256"] = "0" * 64
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ResearchDataError, match="provenance"):
        build_evidence(corpus_dir, context)
