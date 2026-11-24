"""Entrenamiento exploratorio v2: fixture BEC + ham público, fuentes externas separadas.

Nunca convierte las etiquetas publicadas por terceros en anotaciones adjudicadas.
El modelo resultante sirve solo para observación (shadow), aun si supera el
diagnóstico; no se estima eficacia BEC real ni se habilita assist.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from research.bec_training.data import load_research_jsonl, split_groups
from research.bec_training.external_benchmark import _load, _score, _sha
from research.bec_training.training import SEED, _counts, _pipeline

THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
MAX_ENRON_TRAIN = 12000


def _key(text: str) -> str:
    return hashlib.sha256(" ".join(text.casefold().split()).encode("utf-8")).hexdigest()


def partition_ham(texts: list[str]) -> tuple[list[str], list[str]]:
    """Reparto estable antes de entrenar; mismos textos normalizados no cruzan."""
    ordered = sorted(texts, key=_key)
    train = [text for text in ordered if int(_key(text)[:8], 16) % 5 != 0]
    validation = [text for text in ordered if int(_key(text)[:8], 16) % 5 == 0]
    if not train or not validation:
        raise ValueError("Not enough benign messages for an independent validation slice")
    if len(train) > MAX_ENRON_TRAIN:
        train = train[:MAX_ENRON_TRAIN]
    if {_key(text) for text in train} & {_key(text) for text in validation}:
        raise ValueError("Benign training/validation overlap")
    return train, validation


def select_threshold(model, positive: list[str], negative: list[str]) -> tuple[float | None, dict]:
    """Select only on validation. External sources are not consulted here."""
    probabilities_pos = model.predict_proba(positive)[:, 1]
    probabilities_neg = model.predict_proba(negative)[:, 1]
    choices = {}
    for threshold in THRESHOLDS:
        counts = _counts(
            [1] * len(positive) + [0] * len(negative),
            [int(value >= threshold) for value in probabilities_pos]
            + [int(value >= threshold) for value in probabilities_neg],
        )
        choices[str(threshold)] = counts
    feasible = [threshold for threshold in THRESHOLDS if choices[str(threshold)]["fpr"] <= 0.05]
    selected = min(feasible, key=lambda t: (-choices[str(t)]["recall"], t)) if feasible else None
    return selected, choices


def train_public_candidate(
    synthetic_path: Path,
    split_path: Path,
    enron_path: Path,
    bec2_path: Path,
    ceas_path: Path,
) -> tuple[dict, object | None]:
    from sklearn import __version__ as sklearn_version

    synthetic_sha = _sha(synthetic_path)
    split = json.loads(split_path.read_text(encoding="utf-8"))
    if (
        split.get("status") != "TECHNICAL_FIXTURE_ONLY"
        or split.get("dataset_sha256") != synthetic_sha
    ):
        raise ValueError("Synthetic fixture/split provenance mismatch")
    cases = load_research_jsonl(synthetic_path)
    by_id = {case.case_id: case for case in cases}
    allocation = split["splits"]
    if set(allocation) != {"train", "validation", "test"} or sorted(
        case_id for ids in allocation.values() for case_id in ids
    ) != sorted(by_id):
        raise ValueError("Synthetic split does not cover the corpus")
    if any(
        {by_id[case_id].group_id for case_id in allocation[left]}
        & {by_id[case_id].group_id for case_id in allocation[right]}
        for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))
    ):
        raise ValueError("Synthetic independence groups overlap")
    if split.get("seed") != SEED or allocation != split_groups(cases, seed=SEED):
        raise ValueError("Synthetic allocation differs from its frozen splitting rule")

    def fixture_text(part: str, is_bec: bool) -> list[str]:
        return [
            f"{by_id[case_id].email.subject}\n{by_id[case_id].email.body_text}"
            for case_id in allocation[part]
            if (by_id[case_id].label.value == "BEC") == is_bec
        ]

    enron_ham, enron_info = _load(enron_path, "enron")
    train_ham, validation_ham = partition_ham(enron_ham)
    train_pos = fixture_text("train", True)
    train_neg = fixture_text("train", False) + train_ham
    validation_pos = fixture_text("validation", True)
    validation_neg = fixture_text("validation", False) + validation_ham
    train_keys = {_key(text) for text in train_pos + train_neg}
    if train_keys & {_key(text) for text in validation_pos + validation_neg}:
        raise ValueError("Training/validation text overlap")
    model = _pipeline((1, 1), 0.1, "balanced", SEED)
    model.fit(train_pos + train_neg, [1] * len(train_pos) + [0] * len(train_neg))
    selected, choices = select_threshold(model, validation_pos, validation_neg)
    report = {
        "status": "PUBLIC_DIAGNOSTIC_TRAINING_ONLY",
        "test_status": "NOT_RUN" if selected is None else "PUBLIC_CROSS_SOURCE_DIAGNOSTIC_ONLY",
        "real_world_validity": "NOT_ESTABLISHED",
        "assist_eligible": False,
        "seed": SEED,
        "sklearn": sklearn_version,
        "training_code_sha256": _sha(Path(__file__)),
        "synthetic_dataset_sha256": synthetic_sha,
        "split_manifest_sha256": _sha(split_path),
        "enron": enron_info,
        "train_counts": {
            "bec_fixture": len(train_pos),
            "legit_fixture": len(train_neg) - len(train_ham),
            "enron_ham": len(train_ham),
        },
        "validation_counts": {
            "bec_fixture": len(validation_pos),
            "legit_fixture": len(validation_neg) - len(validation_ham),
            "enron_ham": len(validation_ham),
        },
        "candidate": {"ngram_range": [1, 1], "C": 0.1, "class_weight": "balanced"},
        "validation": choices,
        "selected": {"threshold": selected},
        "external_test": None,
    }
    if selected is None:
        report["status"] = "NO_FEASIBLE_PUBLIC_VALIDATION_THRESHOLD"
        return report, None
    bec2, bec2_info = _load(bec2_path, "bec2")
    ceas, ceas_info = _load(ceas_path, "ceas08")
    if train_keys & {_key(text) for text in bec2 + ceas} or {
        _key(text) for text in validation_pos + validation_neg
    } & {_key(text) for text in bec2 + ceas}:
        raise ValueError("Exact cross-source training/evaluation overlap")
    report["external_test"] = {
        "bec2": {**bec2_info, **_score(model, bec2, selected, positive=True)},
        "ceas08_ham": {**ceas_info, **_score(model, ceas, selected, positive=False)},
    }
    report["diagnostic_gate"] = (
        "MEETS_PROXY_TARGETS"
        if report["external_test"]["bec2"]["recall"] >= 0.6
        and report["external_test"]["ceas08_ham"]["fpr"] <= 0.05
        else "FAILS_PROXY_TARGETS"
    )
    return report, model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("synthetic", "split", "enron", "bec2", "ceas08"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report, model = train_public_candidate(
        args.synthetic, args.split, args.enron, args.bec2, args.ceas08
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    if model is not None:
        import joblib

        model_path = args.output_dir / "model.joblib"
        joblib.dump(model, model_path)
        report["model_sha256"] = _sha(model_path)
    report_path = args.output_dir / "training_report.json"
    descriptor = os.open(report_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "selected": report["selected"],
                "diagnostic_gate": report.get("diagnostic_gate"),
                "external_test": report["external_test"],
            }
        )
    )


if __name__ == "__main__":
    main()
