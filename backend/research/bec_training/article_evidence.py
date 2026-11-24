"""Exporta evidencia agregada del fixture para un artículo técnico reproducible.

No consulta proveedores ni modifica el modelo. Reutiliza el test sintético ya
evaluado; sus números nunca representan una prueba independiente del mundo real.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import TrainedModelSettings
from app.services.trained_model import ModelPrediction, assisted_score, predict_email
from research.bec_training import training
from research.bec_training.data import (
    CorpusUse,
    ResearchDataError,
    load_research_jsonl,
    split_groups,
)
from research.bec_training.experiments import compare_offline
from research.bec_training.inputs import load_context_bytes
from research.bec_training.training import _counts


def _metrics(cases, predictions: dict[str, bool]) -> dict:
    truth = [int(case.label.value == "BEC") for case in cases]
    scores = [int(predictions[case.case_id]) for case in cases]
    result = _counts(truth, scores)
    result["total"] = len(cases)
    result["hard_negative_false_alerts"] = sum(
        predictions[case.case_id] for case in cases if case.is_hard_negative
    )
    return result


def build_evidence(corpus_dir: Path, context_path: Path) -> dict:
    dataset_path = corpus_dir / "dataset.jsonl"
    dataset_bytes = dataset_path.read_bytes()
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    split = json.loads((corpus_dir / "split_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((corpus_dir / "model" / "training_report.json").read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "SYNTHETIC_TRAINING_ONLY"
        or split.get("status") != "TECHNICAL_FIXTURE_ONLY"
        or report.get("status") != "TECHNICAL_FIXTURE_ONLY"
        or report.get("test_status") != "FIXTURE_DEMO_ONLY"
        or any(row.get("dataset_sha256") != dataset_hash for row in (manifest, split, report))
        or split.get("seed") != report.get("seed")
    ):
        raise ResearchDataError("Synthetic artifact provenance does not match")
    cases = load_research_jsonl(dataset_path)
    if any(case.annotation_status != "SYNTHETIC_GENERATED" for case in cases):
        raise ResearchDataError("Article fixture contains unexpected annotations")
    if (
        manifest.get("total_cases") != len(cases)
        or manifest.get("groups") != len({case.group_id for case in cases})
        or manifest.get("labels") != dict(Counter(case.label.value for case in cases))
        or report.get("training_code_sha256")
        != hashlib.sha256(Path(training.__file__).read_bytes()).hexdigest()
    ):
        raise ResearchDataError("Synthetic generator or training provenance does not match")
    by_id = {case.case_id: case for case in cases}
    splits = split["splits"]
    if set(splits) != {"train", "validation", "test"} or (
        sorted(case_id for ids in splits.values() for case_id in ids) != sorted(by_id)
    ):
        raise ResearchDataError("Split does not cover every case exactly once")
    groups = [{by_id[case_id].group_id for case_id in splits[part]} for part in splits]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
        raise ResearchDataError("Independence groups overlap across splits")
    if splits != split_groups(cases, seed=split["seed"]) or report["split_counts"] != {
        part: dict(Counter(by_id[case_id].label.value for case_id in ids))
        for part, ids in splits.items()
    }:
        raise ResearchDataError("Split does not match frozen training allocation")
    test_cases = [by_id[case_id] for case_id in splits["test"]]
    context, context_sha256 = load_context_bytes(context_path.read_bytes(), use=CorpusUse())
    experiment = compare_offline(test_cases, context)
    rule_rows = experiment["C1"]
    assert isinstance(rule_rows, list)
    rule_score = {row["case_id"]: row["score"] for row in rule_rows}

    model_path = corpus_dir / "model" / "model.joblib"
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    settings = TrainedModelSettings(
        _env_file=None,
        bec_model_mode="shadow",
        bec_model_path=model_path,
        bec_model_sha256=model_sha256,
        bec_model_report_path=corpus_dir / "model" / "training_report.json",
        bec_model_report_sha256=hashlib.sha256(
            (corpus_dir / "model" / "training_report.json").read_bytes()
        ).hexdigest(),
    )
    model_only: dict[str, bool] = {}
    rule_only: dict[str, bool] = {}
    assisted: dict[str, bool] = {}
    for case in test_cases:
        prediction = predict_email(case.email, settings)
        assert prediction is not None
        score = rule_score[case.case_id]
        assert type(score) is int
        model_only[case.case_id] = prediction.score >= 50
        rule_only[case.case_id] = score >= 50
        # Contrafactual del fixture, sin habilitar assist en el producto.
        assisted[case.case_id] = (
            assisted_score(
                score,
                ModelPrediction(
                    "assist", prediction.probability, prediction.score, prediction.sha256
                ),
            )
            >= 50
        )
    model_metrics = _metrics(test_cases, model_only)
    if any(model_metrics[key] != report["test"][key] for key in ("tp", "fp", "tn", "fn")):
        raise ResearchDataError("Stored model and frozen test report disagree")
    baseline = {case.case_id: False for case in test_cases}
    return {
        "status": "SYNTHETIC_FIXTURE_REUSE_DESCRIPTIVE_ONLY",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": dataset_hash,
        "model_sha256": model_sha256,
        "context_sha256": context_sha256,
        "split_manifest_sha256": hashlib.sha256(
            (corpus_dir / "split_manifest.json").read_bytes()
        ).hexdigest(),
        "training_report_sha256": hashlib.sha256(
            (corpus_dir / "model" / "training_report.json").read_bytes()
        ).hexdigest(),
        "evidence_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "git_commit": split.get("git_commit"),
        "split_seed": split["seed"],
        "model_threshold": report["selected"]["threshold"],
        "labels": dict(Counter(case.label.value for case in cases)),
        "total_groups": len({case.group_id for case in cases}),
        "split_counts": report["split_counts"],
        "test_hard_negatives": sum(case.is_hard_negative for case in test_cases),
        "test_results": {
            "majority_baseline": _metrics(test_cases, baseline),
            "rules_C1": _metrics(test_cases, rule_only),
            "trained_model": model_metrics,
            "rules_plus_model_assist": _metrics(test_cases, assisted),
        },
        "semantic_conditions": "NOT_RUN",
        "real_world_validity": "NOT_ESTABLISHED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = build_evidence(args.corpus_dir, args.context)
        payload = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
    except OSError, ValueError, KeyError, TypeError:
        parser.exit(1, "No se pudo verificar el corpus o escribir evidencia nueva.\n")
    print(json.dumps({"status": evidence["status"], "test_results": evidence["test_results"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
