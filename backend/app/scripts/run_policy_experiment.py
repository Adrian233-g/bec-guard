"""Run the development-only policy search without calling an LLM or writing DB rows."""

import argparse
import json
from pathlib import Path

from app.evaluation.policy_experiment import (
    PolicyExperimentReport,
    constant_semantic_scores,
    run_policy_search,
)
from app.scripts.check_development import DEFAULT_CONTEXT_PATH, load_synthetic_context
from app.services.dataset import DEFAULT_DATASET_PATH, load_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT_PATH)
    parser.add_argument(
        "--semantic-score",
        type=int,
        nargs="+",
        default=[20, 50, 80],
        help="Hypothetical constant scores; arithmetic scenarios, never model measurements.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    cases = load_dataset(args.dataset)
    context = load_synthetic_context(args.context)
    development = [case for case in cases if case.split.value == "development"]
    reports: list[PolicyExperimentReport] = []
    for score in args.semantic_score:
        reports.append(
            run_policy_search(
                development,
                context,
                constant_semantic_scores(development, score),
                seed=args.seed,
                semantic_source="hypothetical",
                estimated_external_calls=0,
            )
        )
    document = {
        "warning": "Hypothetical semantic scores are not model measurements",
        "split": "development",
        "provider_calls": 0,
        "reports": [report.model_dump(mode="json") for report in reports],
    }
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
