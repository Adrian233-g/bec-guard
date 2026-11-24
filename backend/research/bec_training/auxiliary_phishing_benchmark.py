"""Stress test sintético de phishing: NO estima recall ni precision de BEC.

Puntúa un CSV público con etiqueta phishing/legítimo sin incorporarlo al
entrenamiento. Guarda solo agregados y hashes, nunca correos individuales.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import zipfile
from collections import Counter
from pathlib import Path

from research.bec_training.external_benchmark import MODEL_SHA256, _sha

MEMBER = "Zero-Day_Phishing_Emails_Corpus.csv"
MEMBER_SHA256 = "21e7e9d1175cf1ebf070b27b522c3992a52086baba8c01684212e4aec5915567"
LABEL_COUNTS = {"0": 29806, "1": 30194}


def _text_key(text: str) -> str:
    return " ".join(text.casefold().split())


def load_phishing_zip(path: Path) -> tuple[dict[str, list[str]], dict]:
    csv.field_size_limit(10**8)
    zip_sha256 = _sha(path)
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != [MEMBER]:
            raise ValueError("Unexpected archive contents")
        member_sha256 = hashlib.sha256(archive.read(MEMBER)).hexdigest()
        if member_sha256 != MEMBER_SHA256:
            raise ValueError("Source CSV differs from the inspected version")
        seen: dict[str, str] = {}
        groups: dict[str, list[str]] = {"0": [], "1": []}
        labels: Counter[str] = Counter()
        duplicates = 0
        with archive.open(MEMBER) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            if reader.fieldnames != ["Subject", "Body", "Label"]:
                raise ValueError("Unexpected phishing CSV columns")
            for row in reader:
                label = row["Label"]
                labels[label] += 1
                if label not in groups:
                    raise ValueError("Unexpected publisher label")
                subject, body = row["Subject"], row["Body"]
                if not subject or not subject.strip() or not body or not body.strip():
                    raise ValueError("Empty subject or body")
                text = f"{subject.strip()}\n{body.strip()}"
                key = _text_key(text)
                if key in seen:
                    if seen[key] != label:
                        raise ValueError("Conflicting publisher labels for the same text")
                    duplicates += 1
                    continue
                seen[key] = label
                groups[label].append(text)
    if dict(labels) != LABEL_COUNTS:
        raise ValueError("Publisher label distribution changed")
    return groups, {
        "zip_sha256": zip_sha256,
        "csv_sha256": member_sha256,
        "source_labels": dict(labels),
        "excluded_exact_duplicates": duplicates,
        "unique_labels": {label: len(texts) for label, texts in groups.items()},
    }


def _count_flags(model, texts: list[str], threshold: float) -> int:
    return sum(
        int((model.predict_proba(texts[start : start + 1024])[:, 1] >= threshold).sum())
        for start in range(0, len(texts), 1024)
    )


def evaluate(zip_path: Path, model_paths: dict[str, tuple[Path, Path]]) -> dict:
    import joblib

    groups, corpus = load_phishing_zip(zip_path)
    results = {}
    for name, (model_path, report_path) in model_paths.items():
        model_sha256 = _sha(model_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if name == "v1" and model_sha256 != MODEL_SHA256:
            raise ValueError("v1 model differs from the frozen artifact")
        if name == "v2" and report.get("model_sha256") != model_sha256:
            raise ValueError("v2 model and report do not match")
        if (
            report.get("status")
            != {
                "v1": "TECHNICAL_FIXTURE_ONLY",
                "v2": "PUBLIC_DIAGNOSTIC_TRAINING_ONLY",
            }[name]
        ):
            raise ValueError("Unexpected model report status")
        threshold = report.get("selected", {}).get("threshold")
        if type(threshold) not in (int, float) or not 0 < threshold < 1:
            raise ValueError("No frozen model threshold")
        model = joblib.load(model_path)  # Only the local, hash-checked artifact.
        if list(model.classes_) != [0, 1]:
            raise ValueError("Unexpected model classes")
        false_alarms = _count_flags(model, groups["0"], threshold)
        flagged_phishing = _count_flags(model, groups["1"], threshold)
        results[name] = {
            "model_sha256": model_sha256,
            "report_sha256": _sha(report_path),
            "threshold": threshold,
            "benign_count": len(groups["0"]),
            "benign_false_alarms": false_alarms,
            "benign_fpr_synthetic": false_alarms / len(groups["0"]),
            "generic_phishing_count": len(groups["1"]),
            "generic_phishing_flagged": flagged_phishing,
            "generic_phishing_flag_rate": flagged_phishing / len(groups["1"]),
            "bec_recall": "NOT_ESTIMABLE_NO_BEC_SUBTYPE_LABEL",
        }
    return {
        "status": "SYNTHETIC_EXTERNAL_GENERIC_PHISHING_STRESS_ONLY",
        "corpus": corpus,
        "code_sha256": _sha(Path(__file__)),
        "models": results,
        "real_world_validity": "NOT_ESTABLISHED",
        "assist_eligible": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-zip", required=True, type=Path)
    for name in ("v1", "v2"):
        parser.add_argument(f"--{name}-model", required=True, type=Path)
        parser.add_argument(f"--{name}-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(
        args.corpus_zip,
        {
            name: (getattr(args, f"{name}_model"), getattr(args, f"{name}_report"))
            for name in ("v1", "v2")
        },
    )
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(
        json.dumps(
            {"status": report["status"], "corpus": report["corpus"], "models": report["models"]}
        )
    )


if __name__ == "__main__":
    main()
