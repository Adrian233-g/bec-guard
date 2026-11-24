"""v3 prospectivo: entrenar en train/validation y abrir test una vez tras freeze.

Solo aplica a BEC sintético etiquetado por UN evaluador, nunca a BEC real.
Ningún cuerpo, predicción individual ni peso se guarda en el informe agregado.
"""

import argparse
import hashlib
import itertools
import json
import warnings
from collections import Counter
from pathlib import Path
from statistics import fmean
from typing import TypedDict

from research.bec_training.external_benchmark import _sha
from research.bec_training.single_review import (
    SEED,
    _allocate,
    _exclusive,
    _heuristic_groups,
    load_decisions,
    load_packet,
    read_source,
)
from research.bec_training.training import _counts, _pipeline

THRESHOLDS = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


class Trial(TypedDict):
    ngram_range: list[int]
    C: float
    class_weight: str
    folds: list[dict]
    mean_recall: float
    mean_fpr: float


def load_frozen(csv_path: Path, review_dir: Path) -> tuple[dict, dict[str, dict]]:
    frozen_path = review_dir / "frozen_manifest.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    triaged = frozen.get("status") == "SINGLE_ANNOTATOR_TRIAGE_FROZEN"
    weakly_labeled = frozen.get("status") == "SINGLE_ANNOTATOR_WEAK_TRAIN_FROZEN"
    if (
        frozen.get("status")
        not in {
            "SINGLE_ANNOTATOR_SYNTHETIC_FROZEN",
            "SINGLE_ANNOTATOR_TRIAGE_FROZEN",
            "SINGLE_ANNOTATOR_WEAK_TRAIN_FROZEN",
        }
        or frozen.get("seed") != SEED
        or frozen.get("source_sha256") != _sha(csv_path)
        or frozen.get("code_sha256") != _sha(Path(__file__).with_name("single_review.py"))
        or frozen.get("training_code_sha256") != _sha(Path(__file__))
        or frozen.get("selection_manifest_sha256") != _sha(review_dir / "selection_manifest.json")
        or frozen.get("annotations_sha256") != _sha(review_dir / "single_annotations.jsonl")
        or frozen.get("test_status") != "SEALED_NOT_EVALUATED"
    ):
        raise ValueError("Frozen cohort provenance does not match")
    packet, digest = load_packet(review_dir / "blind_packet.jsonl")
    if frozen.get("packet_sha256") != digest:
        raise ValueError("Blind packet changed after freeze")
    decisions = load_decisions(review_dir / "single_annotations.jsonl", packet_sha256=digest)
    if {row.reviewer_id for row in decisions.values()} != {frozen.get("reviewer_id")}:
        raise ValueError("Incomplete or changed single-review annotations")
    triage: dict = {}
    weak: dict = {}
    required: set[str] = set()
    weak_train: set[str] = set()
    if triaged or weakly_labeled:
        from research.bec_training.triage_workflow import _split_by_publisher

        triage_path = review_dir / "triage_manifest.json"
        triage = json.loads(triage_path.read_text(encoding="utf-8"))
        if (
            frozen.get("triage_manifest_sha256") != _sha(triage_path)
            or (
                triaged
                and frozen.get("triage_code_sha256")
                != _sha(Path(__file__).with_name("triage_workflow.py"))
            )
            or triage.get("rules_code_sha256") != _sha(Path(__file__).with_name("triage_rules.py"))
            or triage.get("status") != "TRIAGE_REVIEW_PENDING"
            or not decisions.keys() <= {row["case_id"] for row in packet}
        ):
            raise ValueError("Incomplete or changed triaged review")
        if weakly_labeled:
            from research.bec_training.ai_drafts import load_drafts
            from research.bec_training.weak_supervision import _plan

            weak_path = review_dir / "weak_train_manifest.json"
            weak = json.loads(weak_path.read_text(encoding="utf-8"))
            drafts_path = review_dir / "ai_drafts.json"
            if (
                frozen.get("weak_train_manifest_sha256") != _sha(weak_path)
                or frozen.get("drafts_sha256") != _sha(drafts_path)
                or frozen.get("weak_code_sha256")
                != _sha(Path(__file__).with_name("weak_supervision.py"))
                or weak.get("code_sha256") != _sha(Path(__file__).with_name("weak_supervision.py"))
                or weak.get("triage_manifest_sha256") != _sha(triage_path)
                or weak.get("status") != "WEAK_TRAIN_HUMAN_EVAL_PENDING"
                or frozen.get("annotation_method") != "WEAK_RULE_TRAIN_BEC_HUMAN_VALIDATION_TEST"
            ):
                raise ValueError("Weak-training provenance changed")
            drafts = load_drafts(
                review_dir,
                packet_sha256=digest,
                triage_sha256=_sha(triage_path),
            )
            # Verify lists after source loading below.
            required = set(weak["review_required"])
            weak_train = set(weak["weak_train_bec"])
        else:
            required = set(triage["review_required"])
        if not required <= decisions.keys():
            raise ValueError("Incomplete required human evaluation labels")
    elif set(decisions) != {row["case_id"] for row in packet}:
        raise ValueError("Incomplete single-review annotations")
    source = read_source(csv_path)
    selection = json.loads((review_dir / "selection_manifest.json").read_text(encoding="utf-8"))
    usable = {}
    for record in selection["selected"]:
        case_id = record["case_id"]
        item = source.get(case_id)
        if (
            item is None
            or item["content_sha256"] != record["content_sha256"]
            or item["source_label"] != record["source_label"]
        ):
            raise ValueError("Source row changed after selection")
        if record["source_label"] == "0":
            usable[case_id] = {**item, "label": "LEGITIMATE"}
        elif weakly_labeled and case_id in weak_train:
            usable[case_id] = {**item, "label": "BEC"}
        elif (
            case_id in decisions
            and (not weakly_labeled or case_id in required)
            and decisions[case_id].label == "BEC"
        ):
            usable[case_id] = {**item, "label": "BEC"}
    splits = frozen["splits"]
    if set(frozen["groups"]) != set(usable) or set(splits) != {
        "train",
        "validation",
        "test",
    }:
        raise ValueError("Frozen cohort/splits changed")
    if triaged or weakly_labeled:
        all_selected = {row["case_id"]: source[row["case_id"]] for row in selection["selected"]}
        if weakly_labeled:
            expected_required, expected_weak_train = _plan(triage, all_selected, drafts)
            if required != set(expected_required) or weak_train != set(expected_weak_train):
                raise ValueError("Frozen weak-training cohorts changed")
        if (
            triage["groups"] != _heuristic_groups(all_selected)
            or triage["publisher_splits"] != _split_by_publisher(all_selected, triage["groups"])
            or frozen["groups"] != {case_id: triage["groups"][case_id] for case_id in usable}
            or splits
            != {
                part: sorted(case_id for case_id in ids if case_id in usable)
                for part, ids in triage["publisher_splits"].items()
            }
        ):
            raise ValueError("Frozen triage group allocation changed")
        if weakly_labeled and frozen.get("label_sources") != {
            "weak_train_BEC": len(weak_train),
            "human_validation_BEC": sum(
                usable[case_id]["label"] == "BEC" for case_id in splits["validation"]
            ),
            "human_test_BEC": sum(usable[case_id]["label"] == "BEC" for case_id in splits["test"]),
            "publisher_benign": 1000,
        }:
            raise ValueError("Weak/human label sources changed")
    elif frozen["groups"] != _heuristic_groups(usable) or splits != _allocate(
        usable, frozen["groups"]
    ):
        raise ValueError("Frozen train/validation/test allocation changed")
    counts = Counter(item["label"] for item in usable.values())
    if any(frozen["counts"].get(key) != counts[key] for key in ("BEC", "LEGITIMATE")):
        raise ValueError("Frozen class counts changed")
    return frozen, usable


def _examples(rows: dict[str, dict], ids: list[str]) -> tuple[list[str], list[int], list[str]]:
    texts = [f"{rows[case_id]['subject']}\n{rows[case_id]['body']}" for case_id in ids]
    labels = [int(rows[case_id]["label"] == "BEC") for case_id in ids]
    return texts, labels, ids


def _fit(model, texts: list[str], labels: list[int]) -> None:
    from sklearn.exceptions import ConvergenceWarning

    with warnings.catch_warnings(record=True) as caught:
        warnings.filterwarnings(
            "ignore", message="'penalty' was deprecated", category=FutureWarning
        )
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(texts, labels)
    if any(issubclass(item.category, ConvergenceWarning) for item in caught):
        raise ValueError("Classifier did not converge within the frozen budget")


def train_v3(csv_path: Path, review_dir: Path, output_dir: Path) -> dict:
    import joblib
    from sklearn import __version__ as sklearn_version
    from sklearn.model_selection import StratifiedGroupKFold

    frozen, rows = load_frozen(csv_path, review_dir)
    x, y, train_ids = _examples(rows, frozen["splits"]["train"])
    xv, yv, _ = _examples(rows, frozen["splits"]["validation"])
    groups = [frozen["groups"][case_id] for case_id in train_ids]
    cv = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED)
    folds = list(cv.split(x, y, groups))
    if any(
        set(y[index] for index in left) != {0, 1} or set(y[index] for index in right) != {0, 1}
        for left, right in folds
    ):
        raise ValueError("Insufficient independent class groups for three CV folds")
    trials: list[Trial] = []
    for ngram, c in itertools.product(((1, 1), (1, 2)), (0.1, 1.0)):
        by_fold = []
        for training, held_out in folds:
            model = _pipeline(ngram, c, "balanced", SEED)
            _fit(model, [x[i] for i in training], [y[i] for i in training])
            predictions = [
                int(p >= 0.5) for p in model.predict_proba([x[i] for i in held_out])[:, 1]
            ]
            by_fold.append(_counts([y[i] for i in held_out], predictions))
        trials.append(
            {
                "ngram_range": list(ngram),
                "C": c,
                "class_weight": "balanced",
                "folds": by_fold,
                "mean_recall": fmean(item["recall"] for item in by_fold),
                "mean_fpr": fmean(item["fpr"] for item in by_fold),
            }
        )
    feasible = [trial for trial in trials if trial["mean_fpr"] <= 0.05]
    candidate = (
        sorted(
            feasible, key=lambda t: (-t["mean_recall"], t["mean_fpr"], t["C"], t["ngram_range"])
        )[0]
        if feasible
        else None
    )
    report = {
        "status": "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED",
        "test_status": "SEALED_NOT_EVALUATED",
        "real_world_validity": "NOT_ESTABLISHED",
        "assist_eligible": False,
        "review_method": frozen["annotation_method"],
        "label_sources": frozen.get("label_sources"),
        "source_sha256": _sha(csv_path),
        "frozen_manifest_sha256": _sha(review_dir / "frozen_manifest.json"),
        "training_code_sha256": _sha(Path(__file__)),
        "seed": SEED,
        "sklearn": sklearn_version,
        "split_counts": {
            split: dict(Counter(rows[case_id]["label"] for case_id in ids))
            for split, ids in frozen["splits"].items()
        },
        "cv": trials,
        "selected": None,
        "validation": None,
    }
    if candidate is None:
        report["status"] = "NO_FEASIBLE_SINGLE_REVIEW_CV"
        output_dir.mkdir(parents=True, exist_ok=False)
        _exclusive(
            output_dir / "training_report.json", (json.dumps(report, indent=2) + "\n").encode()
        )
        return report
    ngram = candidate["ngram_range"]
    model = _pipeline((ngram[0], ngram[1]), candidate["C"], "balanced", SEED)
    _fit(model, x, y)
    scores = model.predict_proba(xv)[:, 1]
    choices = {
        str(threshold): _counts(yv, [int(value >= threshold) for value in scores])
        for threshold in THRESHOLDS
    }
    valid = [
        t for t in THRESHOLDS if choices[str(t)]["fpr"] <= 0.05 and choices[str(t)]["recall"] >= 0.6
    ]
    threshold = min(valid, key=lambda t: (-choices[str(t)]["recall"], t)) if valid else None
    report["validation"] = choices
    report["selected"] = {
        "ngram_range": candidate["ngram_range"],
        "C": candidate["C"],
        "class_weight": "balanced",
        "threshold": threshold,
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    if threshold is None:
        report["status"] = "NO_FEASIBLE_SINGLE_REVIEW_THRESHOLD"
    else:
        model_path = output_dir / "model.joblib"
        joblib.dump(model, model_path)
        report["model_sha256"] = _sha(model_path)
        report["selection_frozen_sha256"] = hashlib.sha256(
            json.dumps(
                {
                    "frozen_manifest_sha256": report["frozen_manifest_sha256"],
                    "training_code_sha256": report["training_code_sha256"],
                    "model_sha256": report["model_sha256"],
                    "selected": report["selected"],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
    _exclusive(
        output_dir / "training_report.json",
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    return report


def _group_intervals(y: list[int], predicted: list[int], groups: list[str]) -> dict:
    import numpy as np

    group_ids = sorted(set(groups))
    positive_groups = {group for index, group in enumerate(groups) if y[index] == 1}
    negative_groups = {group for index, group in enumerate(groups) if y[index] == 0}
    if len(group_ids) < 20 or min(len(positive_groups), len(negative_groups)) < 5:
        return {"status": "NOT_ESTIMABLE_INSUFFICIENT_GROUPS"}
    by_group = {
        group: [i for i, value in enumerate(groups) if value == group] for group in group_ids
    }
    rng = np.random.default_rng(SEED)
    recall, fpr = [], []
    for _ in range(2000):
        indexes = [i for group in rng.choice(group_ids, len(group_ids)) for i in by_group[group]]
        metrics = _counts([y[i] for i in indexes], [predicted[i] for i in indexes])
        if metrics["recall"] is not None and metrics["fpr"] is not None:
            recall.append(metrics["recall"])
            fpr.append(metrics["fpr"])
    if len(recall) < 1000:
        return {"status": "NOT_ESTIMABLE_INSUFFICIENT_RESAMPLES"}
    return {
        "status": "ESTIMATED_DESCRIPTIVE_GROUP_BOOTSTRAP",
        "groups": len(group_ids),
        "resamples": len(recall),
        "recall_95": [float(np.quantile(recall, q)) for q in (0.025, 0.975)],
        "fpr_95": [float(np.quantile(fpr, q)) for q in (0.025, 0.975)],
    }


def evaluate_test_once(
    csv_path: Path, review_dir: Path, model_dir: Path, lock_dir: Path, output: Path
) -> dict:
    import joblib

    frozen, rows = load_frozen(csv_path, review_dir)
    report_path = model_dir / "training_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    model_path = model_dir / "model.joblib"
    if (
        report.get("status") != "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED"
        or report.get("frozen_manifest_sha256") != _sha(review_dir / "frozen_manifest.json")
        or report.get("training_code_sha256") != _sha(Path(__file__))
        or report.get("model_sha256") != _sha(model_path)
        or report.get("selected", {}).get("threshold") is None
        or output.exists()
    ):
        raise ValueError("Model/test freeze does not match or output already exists")
    x, y, ids = _examples(rows, frozen["splits"]["test"])
    test_groups = [frozen["groups"][case_id] for case_id in ids]
    lock_dir.mkdir(parents=True, exist_ok=True)
    # One opening for this frozen cohort, independent of how many models are trained.
    lock_path = lock_dir / f"{report['frozen_manifest_sha256']}.json"
    _exclusive(
        lock_path,
        (
            json.dumps(
                {
                    "report_sha256": _sha(report_path),
                    "model_sha256": report["model_sha256"],
                    "selection_frozen_sha256": report["selection_frozen_sha256"],
                }
            )
            + "\n"
        ).encode(),
    )
    model = joblib.load(model_path)  # Local hash-pinned artifact only.
    if list(model.classes_) != [0, 1]:
        raise ValueError("Unexpected model classes")
    predicted = [int(p >= report["selected"]["threshold"]) for p in model.predict_proba(x)[:, 1]]
    result = {
        "status": "SINGLE_ANNOTATOR_SYNTHETIC_FINAL_TEST",
        "source_sha256": frozen["source_sha256"],
        "annotation_method": frozen["annotation_method"],
        "group_method": frozen["group_method"],
        "frozen_manifest_sha256": report["frozen_manifest_sha256"],
        "training_report_sha256": _sha(report_path),
        "selection_frozen_sha256": report["selection_frozen_sha256"],
        "model_sha256": report["model_sha256"],
        "test_count": len(ids),
        "test_groups": len(set(test_groups)),
        "threshold": report["selected"]["threshold"],
        "confusion": _counts(y, predicted),
        "group_bootstrap": _group_intervals(y, predicted, test_groups),
        "objective_met": None,
        "real_world_validity": "NOT_ESTABLISHED",
        "assist_eligible": False,
    }
    confusion = result["confusion"]
    result["objective_met"] = confusion["recall"] >= 0.6 and confusion["fpr"] <= 0.05
    _exclusive(output, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("train", "test"))
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--lock-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.operation == "train":
        report = train_v3(args.csv, args.review_dir, args.model_dir)
        print(json.dumps({"status": report["status"], "selected": report["selected"]}))
    else:
        if args.lock_dir is None or args.output is None:
            parser.error("test requires --lock-dir and --output")
        result = evaluate_test_once(
            args.csv, args.review_dir, args.model_dir, args.lock_dir, args.output
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "confusion": result["confusion"],
                    "objective_met": result["objective_met"],
                }
            )
        )


if __name__ == "__main__":
    main()
