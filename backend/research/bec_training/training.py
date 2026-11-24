"""Baseline entrenable y CV agrupada, solo en memoria y fuera del producto."""

import hashlib
import itertools
import json
import os
import re
import time
import warnings
from collections import Counter
from pathlib import Path
from statistics import fmean, pstdev
from typing import TypedDict

from research.bec_training.data import (
    FIXTURE,
    MAX_CASES,
    SEED,
    CorpusUse,
    ResearchCase,
    ResearchDataError,
    split_groups,
)

THRESHOLDS = (0.4, 0.5, 0.6)
MAX_TRAIN_SECONDS = 2 * 60 * 60


class Trial(TypedDict):
    ngram_range: list[int]
    C: float
    class_weight: str | None
    folds: list[dict]
    converged: bool
    mean_recall: float
    mean_fpr: float
    recall_std: float
    fpr_std: float
    dispersion: float


def _text(case: ResearchCase) -> str:
    # Nunca incorporar etiquetas, IDs, remitente, origen o metadatos a las features.
    return f"{case.email.subject}\n{case.email.body_text}"


def _counts(actual: list[int], predicted: list[int]) -> dict:
    tp = int(sum(a == 1 and p == 1 for a, p in zip(actual, predicted, strict=True)))
    fp = int(sum(a == 0 and p == 1 for a, p in zip(actual, predicted, strict=True)))
    fn = int(sum(a == 1 and p == 0 for a, p in zip(actual, predicted, strict=True)))
    tn = int(sum(a == 0 and p == 0 for a, p in zip(actual, predicted, strict=True)))
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "recall": tp / (tp + fn) if tp + fn else None,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
    }


def _pipeline(ngram_range: tuple[int, int], c: float, class_weight: str | None, seed: int):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=ngram_range, min_df=2, max_df=1.0, sublinear_tf=True, norm="l2"
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    C=c,
                    class_weight=class_weight,
                    penalty="l2",
                    solver="liblinear",
                    tol=1e-4,
                    max_iter=1000,
                    random_state=seed,
                ),
            ),
        ]
    )


def _calibration_sanity(truth: list[int], probabilities) -> dict:
    """Predeclared validation sanity check, not a claim of calibrated probabilities."""
    if len(truth) < 20 or set(truth) != {0, 1}:
        return {"status": "NOT_ESTIMABLE", "minimum_cases": 20}
    brier = sum(
        (probability - actual) ** 2
        for probability, actual in zip(probabilities, truth, strict=True)
    ) / len(truth)
    prevalence = sum(truth) / len(truth)
    reference_brier = prevalence * (1 - prevalence)
    return {
        "status": "PASSED" if brier <= 0.25 and brier <= reference_brier else "FAILED",
        "brier": brier,
        "reference_brier": reference_brier,
        "minimum_cases": 20,
    }


def _claim_final_test(
    lock_dir: Path, *, dataset_sha256: str, selection_frozen_sha256: str, seed: int
) -> Path:
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{dataset_sha256}.json"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ResearchDataError("Final test is already claimed for this dataset") from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(
            {
                "dataset_sha256": dataset_sha256,
                "selection_frozen_sha256": selection_frozen_sha256,
                "seed": seed,
            },
            output,
            indent=2,
        )
    return lock_path


def train_offline(
    cases: list[ResearchCase],
    *,
    seed: int = SEED,
    evaluate_test: bool = False,
    use: CorpusUse = FIXTURE,
    dataset_sha256: str | None = None,
    test_lock_dir: Path | None = None,
    max_seconds: float = MAX_TRAIN_SECONDS,
) -> tuple[dict, object | None]:
    """Devuelve reporte sin correos y modelo en memoria (o None si no hay candidato factible).

    La evaluación de test se solicita una sola vez DESPUÉS de seleccionar configuración y
    umbral en train/validation; nunca se consulta para seleccionar hiperparámetros.
    """
    from sklearn import __version__ as sklearn_version
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.model_selection import StratifiedGroupKFold

    if len(cases) > MAX_CASES:
        raise ResearchDataError("Corpus exceeds offline training budget")
    if max_seconds <= 0:
        raise ResearchDataError("Training time budget must be positive")
    if use.role != "training":
        raise ResearchDataError("Independent evaluation cases cannot train a model")
    if use.kind == "authorized" and (
        dataset_sha256 is None or not re.fullmatch(r"[0-9a-f]{64}", dataset_sha256)
    ):
        raise ResearchDataError("Authorized training requires a dataset SHA-256")
    allocation = split_groups(cases, seed=seed, use=use)
    started_at = time.perf_counter()

    def check_budget() -> None:
        if time.perf_counter() - started_at > max_seconds:
            raise ResearchDataError("Training exceeded the configured CPU time budget")

    by_id = {case.case_id: case for case in cases}
    train = [by_id[key] for key in allocation["train"]]
    validation = [by_id[key] for key in allocation["validation"]]
    test = [by_id[key] for key in allocation["test"]]
    x = [_text(case) for case in train]
    y = [int(case.label.value == "BEC") for case in train]
    groups = [case.group_id for case in train]
    baseline_class = Counter(y).most_common(1)[0][0] if y.count(1) != y.count(0) else 0
    cv = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=seed)
    folds = list(cv.split(x, y, groups))
    for in_fold, held_out in folds:
        if set(groups[i] for i in in_fold) & set(groups[i] for i in held_out):
            raise ResearchDataError("CV independence groups overlap")
        if set(y[i] for i in in_fold) != {0, 1} or set(y[i] for i in held_out) != {0, 1}:
            raise ResearchDataError("Insufficient groups/classes for three CV folds")
    trials: list[Trial] = []
    for ngram, c, weight in itertools.product(
        ((1, 1), (1, 2)), (0.1, 1.0, 10.0), (None, "balanced")
    ):
        fold_results = []
        converged = True
        for in_fold, held_out in folds:
            model = _pipeline(ngram, c, weight, seed)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ConvergenceWarning)
                model.fit([x[i] for i in in_fold], [y[i] for i in in_fold])
            check_budget()
            converged &= not any(issubclass(w.category, ConvergenceWarning) for w in caught)
            fold_results.append(
                _counts(
                    [y[i] for i in held_out],
                    list(model.predict([x[i] for i in held_out])),
                )
            )
        trials.append(
            {
                "ngram_range": list(ngram),
                "C": c,
                "class_weight": weight,
                "folds": fold_results,
                "converged": converged,
                "mean_recall": fmean(item["recall"] for item in fold_results),
                "mean_fpr": fmean(item["fpr"] for item in fold_results),
                "recall_std": pstdev(item["recall"] for item in fold_results),
                "fpr_std": pstdev(item["fpr"] for item in fold_results),
                "dispersion": pstdev(item["recall"] for item in fold_results)
                + pstdev(item["fpr"] for item in fold_results),
            }
        )
    feasible = [row for row in trials if row["converged"] and row["mean_fpr"] <= 0.05]
    selected = (
        sorted(
            feasible,
            key=lambda row: (
                -row["mean_recall"],
                row["mean_fpr"],
                row["dispersion"],
                row["C"],
                row["ngram_range"],
            ),
        )[0]
        if feasible
        else None
    )
    report = {
        "status": "TECHNICAL_FIXTURE_ONLY"
        if use.kind == "fixture"
        else "AUTHORIZED_TRAINING_VALIDATION",
        "corpus_use": use.model_dump(),
        "dataset_sha256": dataset_sha256,
        "training_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "seed": seed,
        "sklearn": sklearn_version,
        "split_counts": {
            key: dict(Counter(by_id[i].label.value for i in ids)) for key, ids in allocation.items()
        },
        "baseline": {
            "class": "BEC" if baseline_class else "LEGITIMATE",
            "validation": _counts(
                [int(c.label.value == "BEC") for c in validation],
                [baseline_class] * len(validation),
            ),
        },
        "cv": trials,
        "selected": None,
        "validation": None,
        "test": None,
        "test_status": "NOT_RUN",
        "calibration": None,
        "resource_budget": {
            "max_seconds": max_seconds,
            "max_cases": 5_000,
            "configurations": 12,
        },
    }
    if selected is None:
        report["status"] = "NO_FEASIBLE_CANDIDATE"
        return report, None
    ngram_range = selected["ngram_range"]
    model = _pipeline(
        (ngram_range[0], ngram_range[1]), selected["C"], selected["class_weight"], seed
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(x, y)
    check_budget()
    if any(issubclass(w.category, ConvergenceWarning) for w in caught):
        report["status"] = "NON_CONVERGED"
        return report, None
    truth = [int(case.label.value == "BEC") for case in validation]
    probabilities = model.predict_proba([_text(case) for case in validation])[:, 1]
    calibration = _calibration_sanity(truth, probabilities)
    report["calibration"] = calibration
    choices = [
        (threshold, _counts(truth, [int(p >= threshold) for p in probabilities]))
        for threshold in THRESHOLDS
    ]
    valid = [choice for choice in choices if choice[1]["fpr"] <= 0.05]
    if use.kind == "authorized" and calibration["status"] != "PASSED":
        valid = []
    threshold = (
        sorted(valid, key=lambda item: (-item[1]["recall"], item[1]["fpr"], item[0]))[0][0]
        if valid
        else None
    )
    report["selected"] = {
        "ngram_range": selected["ngram_range"],
        "C": selected["C"],
        "class_weight": selected["class_weight"],
        "n_iter": int(model.named_steps["classifier"].n_iter_[0]),
        "threshold": threshold,
    }
    report["validation"] = {str(value): result for value, result in choices}
    report["selection_frozen_sha256"] = hashlib.sha256(
        json.dumps(
            {
                "dataset_sha256": dataset_sha256,
                "training_code_sha256": report["training_code_sha256"],
                "seed": seed,
                "selected": report["selected"],
                "calibration": report["calibration"],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if threshold is None:
        report["status"] = (
            "CALIBRATION_NOT_ESTIMABLE"
            if use.kind == "authorized" and calibration["status"] != "PASSED"
            else "NO_FEASIBLE_THRESHOLD"
        )
        return report, model
    if evaluate_test:
        if use.kind == "authorized":
            if test_lock_dir is None:
                raise ResearchDataError(
                    "Authorized final test requires a persistent test lock directory"
                )
            _claim_final_test(
                test_lock_dir,
                dataset_sha256=dataset_sha256 or "",
                selection_frozen_sha256=report["selection_frozen_sha256"],
                seed=seed,
            )
        truth = [int(case.label.value == "BEC") for case in test]
        scores = model.predict_proba([_text(case) for case in test])[:, 1]
        report["test"] = _counts(truth, [int(score >= threshold) for score in scores])
        report["test_status"] = (
            "FIXTURE_DEMO_ONLY" if use.kind == "fixture" else "AUTHORIZED_TEST_EVALUATED"
        )
    return report, model
