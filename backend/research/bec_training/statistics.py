"""Contrastes pareados preespecificados; solo para evaluación nueva autorizada."""

import random
from collections import defaultdict
from math import ceil, floor, sqrt

from app.evaluation.inference import holm_adjust, mcnemar_exact
from research.bec_training.data import SEED, ResearchDataError
from research.bec_training.training import _counts

COMPARISONS = ("C1", "C2")
RESAMPLES = 2000


def _interval(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "lower": ordered[max(0, floor(0.025 * len(ordered)))],
        "upper": ordered[min(len(ordered) - 1, ceil(0.975 * len(ordered)) - 1)],
    }


def paired_inference(experiment: dict, *, seed: int = SEED) -> dict:
    """Bootstrap por grupos y McNemar/Holm en la intersección de casos COMPLETED.

    No produce p-valores si faltan pares, grupos, clases o suficientes discordancias.
    La declaración de autorización/procedencia es un requisito, no su verificación legal.
    """
    use = experiment["corpus_use"]
    if (use["kind"], use["role"], experiment["semantic_source"]) != (
        "authorized",
        "independent_evaluation",
        "CACHED_AUTHORIZED",
    ):
        return {"status": "NOT_EXECUTED", "reason": "INDEPENDENT_AUTHORIZED_CACHE_REQUIRED"}
    if any(experiment[condition] == "NOT_RUN" for condition in ("C1", "C2", "C3")):
        return {"status": "NOT_EXECUTED", "reason": "MISSING_PAIRED_CONDITIONS"}
    indexed = {}
    for condition in ("C1", "C2", "C3"):
        rows = experiment[condition]
        indexed[condition] = {row["case_id"]: row for row in rows}
        if len(indexed[condition]) != len(rows):
            raise ResearchDataError("Duplicate paired case identity")
    if len({frozenset(rows) for rows in indexed.values()}) != 1:
        raise ResearchDataError("Conditions must cover the same case IDs")
    common = sorted(
        case_id
        for case_id in indexed["C3"]
        if all(indexed[key][case_id]["status"] == "COMPLETED" for key in indexed)
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for case_id in common:
        base = indexed["C3"][case_id]
        for key in ("C1", "C2"):
            other = indexed[key][case_id]
            if (base["label"], base["group_id"]) != (other["label"], other["group_id"]):
                raise ResearchDataError("Paired annotations or groups differ")
        grouped[base["group_id"]].append(case_id)
    positive_groups = sum(
        any(indexed["C3"][case_id]["label"] == "BEC" for case_id in ids) for ids in grouped.values()
    )
    negative_groups = sum(
        any(indexed["C3"][case_id]["label"] == "LEGITIMATE" for case_id in ids)
        for ids in grouped.values()
    )
    if len(grouped) < 20 or min(positive_groups, negative_groups) < 5:
        return {
            "status": "NOT_ESTIMABLE",
            "reason": "INSUFFICIENT_PAIRED_GROUPS_OR_CLASSES",
            "pairs": len(common),
            "groups": len(grouped),
        }

    comparisons = {}
    p_values = []
    rng = random.Random(seed)
    group_ids = sorted(grouped)
    for baseline in COMPARISONS:
        left = indexed["C3"]
        right = indexed[baseline]
        correctness_left = [left[key]["alert"] == (left[key]["label"] == "BEC") for key in common]
        correctness_right = [
            right[key]["alert"] == (right[key]["label"] == "BEC") for key in common
        ]
        mcnemar = mcnemar_exact(correctness_left, correctness_right)
        discordant = mcnemar.discordant_left + mcnemar.discordant_right
        differences: dict[str, list[float]] = {"recall": [], "fpr": []}
        for _ in range(RESAMPLES):
            sample = [
                key for group in rng.choices(group_ids, k=len(group_ids)) for key in grouped[group]
            ]
            actual = [int(left[key]["label"] == "BEC") for key in sample]
            if not 0 < sum(actual) < len(actual):
                continue
            metrics_left = _counts(actual, [int(left[key]["alert"]) for key in sample])
            metrics_right = _counts(actual, [int(right[key]["alert"]) for key in sample])
            differences["recall"].append(metrics_left["recall"] - metrics_right["recall"])
            differences["fpr"].append(metrics_left["fpr"] - metrics_right["fpr"])
        if len(differences["recall"]) < int(RESAMPLES * 0.95):
            return {"status": "NOT_ESTIMABLE", "reason": "BOOTSTRAP_CLASS_COVERAGE"}
        actual = [int(left[key]["label"] == "BEC") for key in common]
        original_left = _counts(actual, [int(left[key]["alert"]) for key in common])
        original_right = _counts(actual, [int(right[key]["alert"]) for key in common])
        comparisons[f"C3_vs_{baseline}"] = {
            "pairs": len(common),
            "groups": len(grouped),
            "discordant_c3_correct": mcnemar.discordant_left,
            "discordant_baseline_correct": mcnemar.discordant_right,
            "difference_recall": original_left["recall"] - original_right["recall"],
            "difference_fpr": original_left["fpr"] - original_right["fpr"],
            "ci95_group_bootstrap": {
                name: _interval(values) for name, values in differences.items()
            },
            "valid_resamples": len(differences["recall"]),
            "p_mcnemar_exact": mcnemar.p_value if discordant >= 10 else None,
            "p_holm": None,
        }
        if discordant >= 10:
            p_values.append(mcnemar.p_value)
    if len(p_values) == len(COMPARISONS):
        for baseline, adjusted in zip(COMPARISONS, holm_adjust(p_values), strict=True):
            comparisons[f"C3_vs_{baseline}"]["p_holm"] = adjusted
        status = "ESTIMATED"
    else:
        status = "DESCRIPTIVE_ONLY_INSUFFICIENT_DISCORDANCES"
        for value in comparisons.values():
            value["p_mcnemar_exact"] = None
    return {
        "status": status,
        "seed": seed,
        "resamples_requested": RESAMPLES,
        "paired_subset": "C1_C2_C3_COMPLETED",
        "comparisons": comparisons,
    }


WILSON_Z = 1.959963984540054
CONDITION_KEYS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


def wilson_interval(successes: int, total: int, *, z: float = WILSON_Z) -> dict | None:
    """Intervalo de Wilson 95 % para una proporción; no usa aproximación normal."""
    if total <= 0 or not 0 <= successes <= total:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    half = (
        z * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    )
    return {"low": max(0.0, centre - half), "high": min(1.0, centre + half), "z": z}


def _rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        "wilson95": wilson_interval(numerator, denominator),
    }


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def _curves(rows: list[dict]) -> dict:
    if any(row["score"] is None for row in rows):
        return {"status": "NOT_ESTIMABLE_INCOMPLETE_COVERAGE"}
    positives = sum(row["label"] == "BEC" for row in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return {"status": "NOT_ESTIMABLE_SINGLE_CLASS"}
    pr_points, roc_points = [], []
    for threshold in sorted({row["score"] for row in rows}, reverse=True):
        predicted = [row["score"] >= threshold for row in rows]
        actual = [row["label"] == "BEC" for row in rows]
        tp = sum(a and p for a, p in zip(actual, predicted, strict=True))
        fp = sum(p and not a for a, p in zip(actual, predicted, strict=True))
        tn = sum(not p and not a for a, p in zip(actual, predicted, strict=True))
        if tp + fp:
            pr_points.append(
                {
                    "threshold": threshold,
                    "recall": tp / positives,
                    "precision": tp / (tp + fp),
                }
            )
        if tp + fp + tn:
            roc_points.append(
                {
                    "threshold": threshold,
                    "tpr": tp / positives,
                    "fpr": fp / (fp + tn) if fp + tn else 0.0,
                }
            )
    return {
        "status": "ESTIMATED_DESCRIPTIVE",
        "precision_recall": sorted(pr_points, key=lambda point: point["recall"]),
        "roc": sorted(roc_points, key=lambda point: point["fpr"]),
    }


def _condition_statistics(rows: list[dict]) -> dict:
    scored = [row for row in rows if row["score"] is not None]
    actual = [int(row["label"] == "BEC") for row in scored]
    alerts = _counts(actual, [int(row["alert"]) for row in scored])
    detection = _counts(actual, [int(row["detect"]) for row in scored])
    latency = sorted(row["elapsed_ms"] for row in rows if row["elapsed_ms"] is not None)
    positives = sum(row["label"] == "BEC" for row in scored)
    negatives = len(scored) - positives
    ranking = None
    if len(scored) == len(rows):
        from research.bec_training.reporting import ranking_metrics

        ranking = ranking_metrics(scored)
    types = {}
    for row in rows:
        if row["label"] == "BEC" and row["bec_type"]:
            entry = types.setdefault(row["bec_type"], {"total": 0, "detected": 0, "alerted": 0})
            entry["total"] += 1
            entry["detected"] += row["detect"] is True
            entry["alerted"] += row["alert"] is True
    hard = [row for row in rows if row["is_hard_negative"]]
    return {
        "total": len(rows),
        "scored": len(scored),
        "errors": sum(row["score"] is None for row in rows),
        "fallback": sum(row["status"] == "FALLBACK" for row in rows),
        "groups": len({row["group_id"] for row in rows}),
        "positives": positives,
        "negatives": negatives,
        "confusion": alerts,
        "detection": detection,
        "precision": alerts["precision"],
        "f1": _f1(alerts["precision"], alerts["recall"]),
        "recall_ci": _rate(alerts["tp"], alerts["tp"] + alerts["fn"]),
        "fpr_ci": _rate(alerts["fp"], alerts["fp"] + alerts["tn"]),
        "specificity_ci": _rate(alerts["tn"], alerts["tn"] + alerts["fp"]),
        "ranking": ranking,
        "curves": _curves(rows),
        "by_bec_type": types,
        "hard_negatives": {
            "total": len(hard),
            "false_alerts": sum(row["alert"] is True for row in hard),
        },
        "latency_ms": {
            "measured": len(latency),
            "median": latency[len(latency) // 2] if latency else None,
            "p95": latency[ceil(0.95 * len(latency)) - 1] if latency else None,
        },
        "alert_threshold": rows[0]["alert_threshold"] if rows else None,
    }


def _paired_comparisons(experiment: dict, *, seed: int, resamples: int) -> dict:
    if any(experiment.get(key) == "NOT_RUN" for key in ("C1", "C3")):
        return {"status": "NOT_EXECUTED", "reason": "MISSING_C1_OR_C3"}
    left = {row["case_id"]: row for row in experiment["C3"]}
    baselines = {"C1": experiment["C1"]}
    if experiment.get("C2") != "NOT_RUN":
        baselines["C2"] = experiment["C2"]
    right = {key: {row["case_id"]: row for row in rows} for key, rows in baselines.items()}
    common = sorted(
        case_id
        for case_id in left
        if all(
            case_id in rows and left[case_id]["status"] == "COMPLETED" for rows in right.values()
        )
        and all(rows[case_id]["status"] == "COMPLETED" for rows in right.values())
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for case_id in common:
        grouped[left[case_id]["group_id"]].append(case_id)
    positive_groups = sum(
        any(left[case_id]["label"] == "BEC" for case_id in ids) for ids in grouped.values()
    )
    negative_groups = sum(
        any(left[case_id]["label"] == "LEGITIMATE" for case_id in ids) for ids in grouped.values()
    )
    if len(grouped) < 20 or min(positive_groups, negative_groups) < 5:
        return {
            "status": "NOT_ESTIMABLE",
            "reason": "INSUFFICIENT_PAIRED_GROUPS_OR_CLASSES",
            "pairs": len(common),
            "groups": len(grouped),
        }
    rng = random.Random(seed)
    group_ids = sorted(grouped)
    comparisons = {}
    raw_p_values = []
    for baseline, rows in right.items():
        correctness_left = [left[key]["alert"] == (left[key]["label"] == "BEC") for key in common]
        correctness_right = [rows[key]["alert"] == (rows[key]["label"] == "BEC") for key in common]
        mcnemar = mcnemar_exact(correctness_left, correctness_right)
        discordant = mcnemar.discordant_left + mcnemar.discordant_right
        differences: dict[str, list[float]] = {"recall": [], "fpr": []}
        for _ in range(resamples):
            sample = [
                key for group in rng.choices(group_ids, k=len(group_ids)) for key in grouped[group]
            ]
            actual = [int(left[key]["label"] == "BEC") for key in sample]
            if not 0 < sum(actual) < len(actual):
                continue
            metrics_left = _counts(actual, [int(left[key]["alert"]) for key in sample])
            metrics_right = _counts(actual, [int(rows[key]["alert"]) for key in sample])
            if metrics_left["recall"] is None or metrics_right["recall"] is None:
                continue
            differences["recall"].append(metrics_left["recall"] - metrics_right["recall"])
            if metrics_left["fpr"] is not None and metrics_right["fpr"] is not None:
                differences["fpr"].append(metrics_left["fpr"] - metrics_right["fpr"])
        valid = len(differences["recall"])
        actual = [int(left[key]["label"] == "BEC") for key in common]
        original_left = _counts(actual, [int(left[key]["alert"]) for key in common])
        original_right = _counts(actual, [int(rows[key]["alert"]) for key in common])
        p_value = mcnemar.p_value if discordant >= 10 else None
        if p_value is not None:
            raw_p_values.append(p_value)
        comparisons[f"C3_vs_{baseline}"] = {
            "pairs": len(common),
            "groups": len(grouped),
            "discordant_c3_correct": mcnemar.discordant_left,
            "discordant_baseline_correct": mcnemar.discordant_right,
            "discordances": discordant,
            "difference_recall": original_left["recall"] - original_right["recall"],
            "difference_fpr": original_left["fpr"] - original_right["fpr"],
            "ci95_group_bootstrap": {
                name: _interval(values) if len(values) >= int(resamples * 0.95) else None
                for name, values in differences.items()
            },
            "valid_resamples": valid,
            "p_mcnemar_exact": p_value,
            "p_holm": None,
        }
    if len(raw_p_values) == len(comparisons) and len(raw_p_values) > 1:
        for comparison, adjusted in zip(
            comparisons.values(), holm_adjust(raw_p_values), strict=True
        ):
            comparison["p_holm"] = adjusted
    return {
        "status": "ESTIMATED_TECHNICAL_ONLY",
        "scientific_inference": "NOT_EXECUTED",
        "seed": seed,
        "resamples_requested": resamples,
        "paired_subset": "C1_C2_C3_COMPLETED",
        "comparisons": comparisons,
    }


def technical_statistics(experiment: dict, *, seed: int = SEED, resamples: int = RESAMPLES) -> dict:
    """Estadística descriptiva y contrastes técnicos para la pantalla del laboratorio.

    Siempre etiqueta el resultado como demostración si el corpus es ficticio o
    los scores son hipotéticos. No reemplaza `paired_inference`, que solo estima
    inferencia científica sobre evaluación independiente autorizada.
    """
    use = experiment["corpus_use"]
    source = experiment["semantic_source"]
    if use["kind"] == "fixture":
        basis = "FIXTURE_DEMONSTRATION_ONLY"
    elif source == "HYPOTHETICAL":
        basis = "HYPOTHETICAL_DEMONSTRATION_ONLY"
    else:
        basis = "AUTHORIZED_DESCRIPTIVE"
    conditions = {}
    for key in CONDITION_KEYS:
        rows = experiment[key]
        conditions[key] = (
            {"status": "NOT_RUN"} if rows == "NOT_RUN" else _condition_statistics(rows)
        )
    return {
        "basis": basis,
        "scientific_inference": "NOT_EXECUTED",
        "disclaimer": (
            "Estadística técnica sobre datos sintéticos o simulados; no es evidencia "
            "científica ni indica eficacia real del detector."
        ),
        "seed": seed,
        "resamples": resamples,
        "semantic_source": source,
        "policies": experiment["policies"],
        "conditions": conditions,
        "paired": _paired_comparisons(experiment, seed=seed, resamples=resamples),
    }
