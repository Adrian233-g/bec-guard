"""Entrena y guarda un modelo técnico sobre un corpus JSONL ya validado."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from research.bec_training.data import CorpusUse, load_research_jsonl
from research.bec_training.training import train_offline


def _write_exclusive(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)


def train_dataset(dataset_path: Path, output_dir: Path, *, evaluate_test: bool) -> dict:
    dataset_bytes = dataset_path.read_bytes()
    dataset_sha256 = hashlib.sha256(dataset_bytes).hexdigest()
    cases = load_research_jsonl(dataset_path, use=CorpusUse())
    report, model = train_offline(
        cases,
        use=CorpusUse(),
        dataset_sha256=dataset_sha256,
        evaluate_test=evaluate_test,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    if model is not None:
        import joblib

        model_path = output_dir / "model.joblib"
        joblib.dump(model, model_path)
        report["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    report_path = output_dir / "training_report.json"
    _write_exclusive(
        report_path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evaluate-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = train_dataset(args.dataset, args.output_dir, evaluate_test=args.evaluate_test)
    except OSError, ValueError:
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "selected": report["selected"],
                "test_status": report["test_status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
