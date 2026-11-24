"""Crea un corpus sintético explícito para entrenamiento técnico offline."""

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from research.bec_training.generate_corpus import GENERATOR_VERSION, SEED, generate_candidates

TRAINING_VERSION = "bec-synthetic-training-v1"


def _jsonl(records: list[dict]) -> str:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )


def _write_exclusive(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(content)


def create_training_dataset(output_dir: Path, *, seed: int = SEED) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    records = generate_candidates(seed)
    for record in records:
        record["annotation_status"] = "SYNTHETIC_GENERATED"
    content = _jsonl(records)
    dataset_path = output_dir / "dataset.jsonl"
    _write_exclusive(dataset_path, content)
    manifest = {
        "dataset_version": TRAINING_VERSION,
        "generator_version": GENERATOR_VERSION,
        "status": "SYNTHETIC_TRAINING_ONLY",
        "purpose": "Technical offline model training; not real-world evaluation",
        "seed": seed,
        "total_cases": len(records),
        "groups": len({record["group_id"] for record in records}),
        "labels": dict(Counter(record["label"] for record in records)),
        "bec_types": dict(
            Counter(
                record["expected_bec_type"] for record in records if record["expected_bec_type"]
            )
        ),
        "hard_negatives": sum(record["is_hard_negative"] for record in records),
        "dataset_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": dataset_path.name,
        "scientific_status": "NOT_EXECUTED",
    }
    _write_exclusive(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    try:
        manifest = create_training_dataset(args.output_dir, seed=args.seed)
    except OSError, ValueError:
        return 1
    print(json.dumps({key: manifest[key] for key in ("status", "total_cases", "groups", "labels")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
