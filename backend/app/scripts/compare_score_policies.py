"""Compare score policies on development emails with hypothetical IA scores.

No provider is called. Fixed semantic scores are stress scenarios, not predictions
or an estimate of model performance. Reserved holdout cases are never evaluated.
"""

import json
from collections import Counter

from app.schemas.dataset import DatasetSplit
from app.scripts.check_development import load_synthetic_context
from app.services.dataset import load_dataset
from app.services.deterministic_analysis import assess_deterministically
from app.services.hybrid_scoring import combine_scores


def candidate_score(deterministic: int, semantic: int) -> int:
    """30/70, rounded half-up, retaining the current strong-rule floor."""
    if any(type(s) is not int or not 0 <= s <= 100 for s in (deterministic, semantic)):
        raise ValueError("Scores must be integers between 0 and 100")
    return max((3 * deterministic + 7 * semantic + 5) // 10, 70 if deterministic >= 70 else 0)


def compare(cases, context, semantic_scores=(20, 50, 80)):
    development = [
        (case.label.value, assess_deterministically(case.email, context).score)
        for case in cases
        if case.split == DatasetSplit.DEVELOPMENT
    ]
    results = {}
    for semantic in semantic_scores:
        counts = {
            name: Counter()
            for name in ("baseline_50_50_70", "threshold_50", "weight_30_70", "both")
        }
        for label, det in development:
            current = combine_scores(det, semantic)
            candidate = candidate_score(det, semantic)
            for name, alert in (
                ("baseline_50_50_70", current >= 70),
                ("threshold_50", current >= 50),
                ("weight_30_70", candidate >= 70),
                ("both", candidate >= 50),
            ):
                counts[name][f"{label}_total"] += 1
                counts[name][f"{label}_alerts"] += int(alert)
        results[str(semantic)] = {name: dict(count) for name, count in counts.items()}
    return results


def main():
    print(
        json.dumps(
            {
                "warning": "Same hypothetical semantic score for all emails; not model accuracy",
                "split": "development",
                "semantic_policy": "fixed hypothetical scenarios; no provider calls",
                "candidate": "30% rules / 70% semantic; retain deterministic >=70 floor",
                "results": compare(load_dataset(), load_synthetic_context()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
