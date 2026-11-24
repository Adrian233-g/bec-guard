"""Evaluación diagnóstica externa del modelo congelado; no entrena ni toca la API.

Entrada: CSV originales de Dube (BEC-2) y Champa et al. (Enron/CEAS 2008).
Salida: solo conteos y hashes; nunca mensajes ni predicciones individuales.
"""

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

MODEL_SHA256 = "7a163d9141c3404ff28d428e2a7f4b14be4010c26811899c36a5840c0cdd0a06"
REPORT_SHA256 = "53842f6734ec11c03a8c505af5a38d0593d5b651d5cb7f8bbabcee33c865b761"
SOURCE = {
    "bec2": {"expected": {"positive": 276, "neutral": 3}, "label": "Human"},
    "enron": {"expected": {"0": 15791, "1": 13976}, "label": "label"},
    "ceas08": {"expected": {"0": 17312, "1": 21842}, "label": "label"},
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, name: str) -> tuple[list[str], dict]:
    csv.field_size_limit(10**8)
    seen: set[str] = set()
    texts: list[str] = []
    labels: Counter[str] = Counter()
    excluded_empty = 0
    excluded_duplicate = 0
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"subject", "body", SOURCE[name]["label"]}.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing expected CSV columns: {name}")
        for row in reader:
            label = row[SOURCE[name]["label"]]
            labels[label] += 1
            if label != ("positive" if name == "bec2" else "0"):
                continue
            subject = (row["subject"] or "").strip()
            body = (row["body"] or "").strip()
            if not subject and not body:
                excluded_empty += 1
                continue
            text = f"{subject}\n{body}"
            key = " ".join(text.casefold().split())
            if key in seen:
                excluded_duplicate += 1
                continue
            seen.add(key)
            texts.append(text)
    if dict(labels) != SOURCE[name]["expected"]:
        raise ValueError(f"Unexpected label distribution: {name}")
    return texts, {
        "sha256": _sha(path),
        "source_rows": sum(labels.values()),
        "source_labels": dict(labels),
        "excluded_empty": excluded_empty,
        "excluded_exact_duplicates": excluded_duplicate,
        "evaluated": len(texts),
    }


def _score(model, texts: list[str], threshold: float, positive: bool) -> dict:
    detected = 0
    for start in range(0, len(texts), 1024):
        probabilities = model.predict_proba(texts[start : start + 1024])[:, 1]
        detected += int((probabilities >= threshold).sum())
    n = len(texts)
    if positive:
        return {"tp": detected, "fn": n - detected, "recall": detected / n if n else None}
    return {"fp": detected, "tn": n - detected, "fpr": detected / n if n else None}


def evaluate(model_path: Path, report_path: Path, paths: dict[str, Path]) -> dict:
    if _sha(model_path) != MODEL_SHA256 or _sha(report_path) != REPORT_SHA256:
        raise ValueError("Frozen model or training report differs from the published artifact")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    threshold = report["selected"]["threshold"]
    if report["status"] != "TECHNICAL_FIXTURE_ONLY" or threshold != 0.5:
        raise ValueError("Unexpected training status or threshold")
    import joblib

    model = joblib.load(model_path)  # Only the locally pinned, hash-verified artifact.
    if list(model.classes_) != [0, 1]:
        raise ValueError("Unexpected model classes")
    cohorts = {}
    for name, path in paths.items():
        texts, provenance = _load(path, name)
        cohorts[name] = {
            **provenance,
            **_score(model, texts, threshold, positive=name == "bec2"),
        }
    positive = cohorts["bec2"]
    negative = [cohorts["enron"], cohorts["ceas08"]]
    tp = positive["tp"]
    fn = positive["fn"]
    fp = sum(cohort["fp"] for cohort in negative)
    tn = sum(cohort["tn"] for cohort in negative)
    return {
        "status": "CROSS_SOURCE_SYNTHETIC_BEC_AND_PUBLIC_HAM_DIAGNOSTIC_ONLY",
        "model_sha256": MODEL_SHA256,
        "training_report_sha256": REPORT_SHA256,
        "benchmark_code_sha256": _sha(Path(__file__)),
        "threshold": threshold,
        "method": "frozen_subject_body; exact_dedup_per_source; published_labels",
        "cohorts": cohorts,
        "constructed_mixture": {
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "tn": tn,
            "positive_prevalence": (tp + fn) / (tp + fn + fp + tn),
            "recall": tp / (tp + fn),
            "fpr": fp / (fp + tn),
            "precision": tp / (tp + fp) if tp + fp else None,
        },
        "real_world_validity": "NOT_ESTABLISHED",
        "operational_rules_and_assist": "NOT_EVALUATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    for name in SOURCE:
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(
        args.model,
        args.report,
        {name: getattr(args, name) for name in SOURCE},
    )
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"cohorts": result["cohorts"], "mixture": result["constructed_mixture"]}))


if __name__ == "__main__":
    main()
