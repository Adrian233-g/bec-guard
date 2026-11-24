"""Etiquetas débiles de TRAIN + verdad de terreno humana en validation/test.

Las decisiones automáticas nunca se registran como revisadas por ADRIAN. La
regla se aplica solo a train; el test permanece sellado y sin sugerencias.
"""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from research.bec_training.ai_drafts import load_drafts
from research.bec_training.external_benchmark import _sha
from research.bec_training.single_review import SEED, _exclusive, load_decisions
from research.bec_training.triage_workflow import _selected_source


def _plan(triage: dict, rows: dict[str, dict], drafts: dict) -> tuple[list[str], list[str]]:
    required = sorted(
        case_id
        for part in ("validation", "test")
        for case_id in triage["publisher_splits"][part]
        if rows[case_id]["source_label"] == "1"
    )
    weak_train = sorted(
        case_id
        for case_id in triage["publisher_splits"]["train"]
        if rows[case_id]["source_label"] == "1"
        and drafts[case_id]["proposed_label"] == "BEC"
        and drafts[case_id]["bucket"] == "POSIBLE_BEC"
        and drafts[case_id]["content_sha256"] == rows[case_id]["content_sha256"]
    )
    if len(required) < 500 or len(weak_train) < 40:
        raise ValueError("Not enough human-evaluation or weak-training candidates")
    return required, weak_train


def _inputs(csv_path: Path, review_dir: Path) -> tuple[dict, dict[str, dict], str, dict]:
    selection, rows, digest = _selected_source(csv_path, review_dir)
    triage_path = review_dir / "triage_manifest.json"
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    if (
        triage.get("status") != "TRIAGE_REVIEW_PENDING"
        or triage.get("source_sha256") != selection["source_sha256"]
        or triage.get("packet_sha256") != digest
        or triage.get("code_sha256") != _sha(Path(__file__).with_name("triage_workflow.py"))
        or triage.get("rules_code_sha256") != _sha(Path(__file__).with_name("triage_rules.py"))
    ):
        raise ValueError("Pinned triage has changed")
    drafts = load_drafts(review_dir, packet_sha256=digest, triage_sha256=_sha(triage_path))
    train_phishing = {
        case_id
        for case_id in triage["publisher_splits"]["train"]
        if rows[case_id]["source_label"] == "1"
    }
    if not drafts or set(drafts) != train_phishing:
        raise ValueError("AI/rule drafts are missing or incomplete")
    return triage, rows, digest, drafts


def prepare_weak(csv_path: Path, review_dir: Path) -> dict:
    triage, rows, digest, drafts = _inputs(csv_path, review_dir)
    required, weak_train = _plan(triage, rows, drafts)
    report = {
        "status": "WEAK_TRAIN_HUMAN_EVAL_PENDING",
        "source_sha256": triage["source_sha256"],
        "packet_sha256": digest,
        "triage_manifest_sha256": _sha(review_dir / "triage_manifest.json"),
        "drafts_sha256": _sha(review_dir / "ai_drafts.json"),
        "code_sha256": _sha(Path(__file__)),
        "seed": SEED,
        "review_required": required,
        "weak_train_bec": weak_train,
        "counts": {
            "human_validation": sum(
                case_id in required for case_id in triage["publisher_splits"]["validation"]
            ),
            "human_test": sum(
                case_id in required for case_id in triage["publisher_splits"]["test"]
            ),
            "weak_train_bec": len(weak_train),
            "train_other_phishing_not_used": sum(
                rows[case_id]["source_label"] == "1" and case_id not in weak_train
                for case_id in triage["publisher_splits"]["train"]
            ),
        },
        "test_status": "SEALED_NOT_EVALUATED",
    }
    _exclusive(
        review_dir / "weak_train_manifest.json",
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    return {key: report[key] for key in ("status", "counts", "test_status")}


def freeze_weak(csv_path: Path, review_dir: Path) -> dict:
    triage, rows, digest, drafts = _inputs(csv_path, review_dir)
    manifest_path = review_dir / "weak_train_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required, weak_train = _plan(triage, rows, drafts)
    if (
        manifest.get("status") != "WEAK_TRAIN_HUMAN_EVAL_PENDING"
        or manifest.get("source_sha256") != triage["source_sha256"]
        or manifest.get("packet_sha256") != digest
        or manifest.get("triage_manifest_sha256") != _sha(review_dir / "triage_manifest.json")
        or manifest.get("drafts_sha256") != _sha(review_dir / "ai_drafts.json")
        or manifest.get("code_sha256") != _sha(Path(__file__))
        or manifest.get("review_required") != required
        or manifest.get("weak_train_bec") != weak_train
    ):
        raise ValueError("Weak-training plan changed after it was fixed")
    annotations_path = review_dir / "single_annotations.jsonl"
    decisions = load_decisions(annotations_path, packet_sha256=digest)
    if not set(required) <= decisions.keys():
        raise ValueError(
            f"Complete {len(set(required) - decisions.keys())} human evaluation labels"
        )
    if {item.reviewer_id for item in decisions.values()} != {"ADRIAN"} or any(
        case_id not in rows or item.content_sha256 != rows[case_id]["content_sha256"]
        for case_id, item in decisions.items()
    ):
        raise ValueError("Human decisions do not match this reviewer/packet")
    usable = {
        case_id: {**row, "label": "LEGITIMATE"}
        for case_id, row in rows.items()
        if row["source_label"] == "0"
    }
    usable.update({case_id: {**rows[case_id], "label": "BEC"} for case_id in weak_train})
    usable.update(
        {
            case_id: {**rows[case_id], "label": "BEC"}
            for case_id in required
            if decisions[case_id].label == "BEC"
        }
    )
    splits = {
        part: sorted(case_id for case_id in ids if case_id in usable)
        for part, ids in triage["publisher_splits"].items()
    }
    counts = {
        part: Counter(usable[case_id]["label"] for case_id in ids) for part, ids in splits.items()
    }
    if any(
        counts[part]["BEC"] < minimum[0] or counts[part]["LEGITIMATE"] < minimum[1]
        for part, minimum in {
            "train": (40, 300),
            "validation": (10, 50),
            "test": (20, 100),
        }.items()
    ):
        raise ValueError("Insufficient human BEC labels in validation/test")
    frozen = {
        "status": "SINGLE_ANNOTATOR_WEAK_TRAIN_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "source_sha256": triage["source_sha256"],
        "selection_manifest_sha256": _sha(review_dir / "selection_manifest.json"),
        "triage_manifest_sha256": _sha(review_dir / "triage_manifest.json"),
        "weak_train_manifest_sha256": _sha(manifest_path),
        "drafts_sha256": _sha(review_dir / "ai_drafts.json"),
        "packet_sha256": digest,
        "annotations_sha256": _sha(annotations_path),
        "reviewer_id": "ADRIAN",
        "code_sha256": _sha(Path(__file__).with_name("single_review.py")),
        "weak_code_sha256": _sha(Path(__file__)),
        "training_code_sha256": _sha(Path(__file__).with_name("single_review_training.py")),
        "seed": SEED,
        "annotation_method": "WEAK_RULE_TRAIN_BEC_HUMAN_VALIDATION_TEST",
        "benign_method": "PUBLISHER_SYNTHETIC_LABEL_0_NOT_REVIEWED",
        "label_sources": {
            "weak_train_BEC": len(weak_train),
            "human_validation_BEC": counts["validation"]["BEC"],
            "human_test_BEC": counts["test"]["BEC"],
            "publisher_benign": 1000,
        },
        "group_method": triage.get("group_method", "HEURISTIC_TEXT_GROUPS_FROM_TRIAGE"),
        "counts": {
            "BEC": sum(row["label"] == "BEC" for row in usable.values()),
            "LEGITIMATE": sum(row["label"] == "LEGITIMATE" for row in usable.values()),
            "OTHER_PHISHING_HUMAN_EXCLUDED": sum(
                decisions[case_id].label == "OTHER_PHISHING" for case_id in required
            ),
            "UNCERTAIN_HUMAN_EXCLUDED": sum(
                decisions[case_id].label == "UNCERTAIN" for case_id in required
            ),
            "TRAIN_PHISHING_UNREVIEWED_EXCLUDED": manifest["counts"][
                "train_other_phishing_not_used"
            ],
        },
        "groups": {case_id: triage["groups"][case_id] for case_id in usable},
        "splits": splits,
        "test_status": "SEALED_NOT_EVALUATED",
        "real_world_validity": "NOT_ESTABLISHED",
        "assist_eligible": False,
    }
    _exclusive(
        review_dir / "frozen_manifest.json",
        (json.dumps(frozen, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    return {key: frozen[key] for key in ("status", "label_sources", "counts", "test_status")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "freeze"))
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        prepare_weak(args.csv, args.review_dir)
        if args.operation == "prepare"
        else freeze_weak(args.csv, args.review_dir)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
