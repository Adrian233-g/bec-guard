"""Validate the corpus and print counts only. Does not connect to PostgreSQL."""

import argparse
import json
import sys
from pathlib import Path

from app.services.dataset import (
    DEFAULT_DATASET_PATH,
    DatasetValidationError,
    dataset_descriptive_summary,
    dataset_summary,
    load_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument(
        "--descriptive",
        action="store_true",
        help="print aggregate development statistics without email content",
    )
    parser.add_argument(
        "--independent",
        action="store_true",
        help="validate a new evaluation-only dataset with independence groups",
    )
    arguments = parser.parse_args()
    try:
        cases = load_dataset(
            arguments.path,
            validate_fixed=not arguments.independent,
            require_group_id=arguments.independent,
        )
        if arguments.independent and any(case.split.value != "evaluation" for case in cases):
            raise DatasetValidationError("Independent dataset must contain only evaluation cases")
    except DatasetValidationError as error:
        print(f"Dataset invalid: {error}", file=sys.stderr)
        return 1
    summary = (
        dataset_descriptive_summary(cases) if arguments.descriptive else dataset_summary(cases)
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
