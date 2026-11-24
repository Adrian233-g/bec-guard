"""Agregados exportables; datos sin correo ni predicciones individuales."""

from collections import Counter
from math import ceil
from statistics import median

from research.bec_training.experiments import CONDITIONS
from research.bec_training.statistics import paired_inference
from research.bec_training.training import _counts


def ranking_metrics(rows: list[dict]) -> dict:
    """Average precision y ROC-AUC con empates, sin imputar scores faltantes."""
    if any(row["score"] is None for row in rows):
        return {"status": "NOT_ESTIMABLE_INCOMPLETE_COVERAGE"}
    positives = sum(row["label"] == "BEC" for row in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return {"status": "NOT_ESTIMABLE_SINGLE_CLASS"}
    buckets: dict[int, Counter] = {}
    for row in rows:
        buckets.setdefault(row["score"], Counter())[row["label"]] += 1
    tp = fp = 0
    average_precision = auc_wins = 0.0
    for score in sorted(buckets, reverse=True):
        pos = buckets[score]["BEC"]
        neg = buckets[score]["LEGITIMATE"]
        tp += pos
        fp += neg
        average_precision += (pos / positives) * (tp / (tp + fp))
        auc_wins += pos * (negatives - fp) + 0.5 * pos * neg
    return {
        "status": "ESTIMATED_DESCRIPTIVE",
        "average_precision": average_precision,
        "roc_auc": auc_wins / (positives * negatives),
        "positives": positives,
        "negatives": negatives,
    }


def summarize_experiment(experiment: dict, *, provenance: dict | None = None) -> dict:
    valid_provenance = {
        key: provenance[key]
        for key in (
            "dataset_sha256",
            "context_sha256",
            "pipeline_sha256",
            "research_code_sha256",
            "dependencies",
            "uv_lock_sha256",
            "git_commit",
            "seed",
            "working_tree_dirty",
        )
        if provenance is not None and key in provenance
    }
    source = experiment["semantic_source"]
    use = experiment["corpus_use"]
    inference = paired_inference(experiment)
    result = {
        "status": "TECHNICAL_FIXTURE_ONLY"
        if use["kind"] == "fixture"
        else "AUTHORIZED_DESCRIPTIVE",
        "corpus_use": use,
        "policies": experiment["policies"],
        "semantic_source": source,
        "semantic_provenance": experiment["semantic_provenance"],
        "no_context_semantic_provenance": experiment["no_context_semantic_provenance"],
        "no_context_cache_sha256": experiment["no_context_cache_sha256"],
        "scientific_inference": inference["status"],
        "paired_statistics": inference,
        "provenance": valid_provenance,
        "conditions": {},
    }
    for condition in CONDITIONS:
        rows = experiment[condition]
        if rows == "NOT_RUN":
            result["conditions"][condition] = {"status": "NOT_RUN"}
            continue
        scored = [row for row in rows if row["score"] is not None]
        actual = [int(row["label"] == "BEC") for row in scored]
        detection = _counts(actual, [int(row["detect"]) for row in scored])
        alerts = _counts(actual, [int(row["alert"]) for row in scored])
        detection["effective_recall"] = (
            detection["tp"] / sum(row["label"] == "BEC" for row in rows)
            if any(row["label"] == "BEC" for row in rows)
            else None
        )
        alerts["effective_recall"] = (
            alerts["tp"] / sum(row["label"] == "BEC" for row in rows)
            if any(row["label"] == "BEC" for row in rows)
            else None
        )
        hard = [row for row in rows if row["is_hard_negative"]]
        timing = sorted(row["elapsed_ms"] for row in rows if row["elapsed_ms"] is not None)
        types = sorted({row["bec_type"] for row in rows if row["bec_type"]})
        result["conditions"][condition] = {
            "status": "RULES_ABLATION_ONLY"
            if condition == "C4" and source == "NOT_RUN"
            else ("HYPOTHETICAL_SIMULATION" if source == "HYPOTHETICAL" else "DESCRIPTIVE_ONLY"),
            "total": len(rows),
            "completed": sum(row["status"] == "COMPLETED" for row in rows),
            "fallback": sum(row["status"] == "FALLBACK" for row in rows),
            "errors": sum(row["status"] == "ERROR" for row in rows),
            "score_coverage": len(scored) / len(rows),
            "semantic_coverage": (
                sum(row["status"] == "COMPLETED" for row in rows) / len(rows)
                if source == "CACHED_AUTHORIZED" and condition in {"C2", "C3", "C4", "C5", "C6"}
                else None
            ),
            "detection": detection,
            "alerts": alerts,
            "ranking": ranking_metrics(rows)
            if not (condition == "C3" and any(row["status"] == "FALLBACK" for row in rows))
            else {"status": "NOT_ESTIMABLE_MIXED_FALLBACK"},
            "hard_negatives": {
                "total": len(hard),
                "scored": sum(row["score"] is not None for row in hard),
                "errors": sum(row["score"] is None for row in hard),
                "false_alerts": sum(row["alert"] is True for row in hard),
            },
            "by_bec_type": {
                kind: {
                    "total": sum(row["bec_type"] == kind for row in rows),
                    "detected": sum(
                        row["bec_type"] == kind and row["detect"] is True for row in rows
                    ),
                    "errors": sum(row["bec_type"] == kind and row["score"] is None for row in rows),
                }
                for kind in types
            },
            "latency_ms": {
                "measured": len(timing),
                "median": median(timing) if timing else None,
                "p95": timing[ceil(0.95 * len(timing)) - 1] if timing else None,
            },
            "alert_threshold": rows[0]["alert_threshold"],
        }
    # Los resultados son siempre agregados; las predicciones por caso no se serializan.
    result["condition_counts"] = dict(
        Counter(value["status"] for value in result["conditions"].values())
    )
    return result
