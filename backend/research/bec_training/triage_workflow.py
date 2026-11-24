"""Triaje predeclarado: revisión humana íntegra de validation/test y train selectivo.

Ninguna salida de la regla equivale a una etiqueta BEC verificada. Los otros
phishing de train que la regla descarta se EXCLUYEN, no se atribuyen a ADRIAN.
"""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from research.bec_training.external_benchmark import _sha
from research.bec_training.single_review import (
    SEED,
    _exclusive,
    _heuristic_groups,
    load_decisions,
    load_packet,
    read_source,
    sampled_ids,
)
from research.bec_training.triage_rules import RULE_VERSION, suggest


def _split_by_publisher(selected: dict[str, dict], groups: dict[str, str]) -> dict[str, list[str]]:
    from sklearn.model_selection import GroupShuffleSplit

    ids = sorted(selected)
    labels = [int(selected[case_id]["source_label"] == "1") for case_id in ids]
    group_ids = [groups[case_id] for case_id in ids]
    best = None
    for attempt in range(128):
        outer = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED + attempt)
        development, test = next(outer.split(ids, labels, group_ids))
        dev_ids = [ids[i] for i in development]
        inner = GroupShuffleSplit(n_splits=1, test_size=0.17647, random_state=SEED + attempt)
        train, validation = next(
            inner.split(
                dev_ids,
                [int(selected[case_id]["source_label"] == "1") for case_id in dev_ids],
                [groups[case_id] for case_id in dev_ids],
            )
        )
        parts = {
            "train": sorted(dev_ids[i] for i in train),
            "validation": sorted(dev_ids[i] for i in validation),
            "test": sorted(ids[i] for i in test),
        }
        counts = {
            part: Counter(selected[case_id]["source_label"] for case_id in case_ids)
            for part, case_ids in parts.items()
        }
        minimums = {
            "train": (1100, 600),
            "validation": (250, 100),
            "test": (250, 100),
        }
        if any(
            counts[part]["1"] < phish or counts[part]["0"] < benign
            for part, (phish, benign) in minimums.items()
        ):
            continue
        score = sum(
            abs(counts[part][label] / (2000 if label == "1" else 1000) - target)
            for part, target in (("train", 0.7), ("validation", 0.15), ("test", 0.15))
            for label in ("0", "1")
        )
        if best is None or score < best[0]:
            best = (score, parts)
    if best is None:
        raise ValueError("No valid grouped train/validation/test allocation for triage")
    return best[1]


def _selected_source(csv_path: Path, review_dir: Path) -> tuple[dict, dict[str, dict], str]:
    source = read_source(csv_path)
    selection_path = review_dir / "selection_manifest.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    packet, digest = load_packet(review_dir / "blind_packet.jsonl")
    if (
        selection.get("status") != "SINGLE_ANNOTATOR_SYNTHETIC_PENDING"
        or selection.get("source_sha256") != _sha(csv_path)
        or selection.get("packet_sha256") != digest
        or selection.get("seed") != SEED
        or selection.get("selection_code_sha256")
        != _sha(Path(__file__).with_name("single_review.py"))
    ):
        raise ValueError("Selected source/packet has changed")
    selected_ids = sampled_ids(source, n_phish=2000, n_benign=1000)
    expected = [
        {
            "case_id": case_id,
            "source_label": label,
            "content_sha256": source[case_id]["content_sha256"],
        }
        for label in ("0", "1")
        for case_id in selected_ids[label]
    ]
    if (
        expected != selection["selected"]
        or {row["case_id"] for row in packet} != set(selected_ids["1"])
        or any(row["content_sha256"] != source[row["case_id"]]["content_sha256"] for row in packet)
    ):
        raise ValueError("Selected rows or blind text do not match the source")
    return selection, {row["case_id"]: source[row["case_id"]] for row in expected}, digest


def prepare_triage(csv_path: Path, review_dir: Path) -> dict:
    selection, rows, digest = _selected_source(csv_path, review_dir)
    groups = _heuristic_groups(rows)
    parts = _split_by_publisher(rows, groups)
    suggestions = {
        case_id: suggest(row["subject"], row["body"]).bucket
        for case_id, row in rows.items()
        if row["source_label"] == "1"
    }
    required = sorted(
        case_id
        for part, ids in parts.items()
        for case_id in ids
        if rows[case_id]["source_label"] == "1"
        and (part != "train" or suggestions[case_id] != "OTRO_CLARO")
    )
    report = {
        "status": "TRIAGE_REVIEW_PENDING",
        "source_sha256": selection["source_sha256"],
        "selection_manifest_sha256": _sha(review_dir / "selection_manifest.json"),
        "packet_sha256": digest,
        "code_sha256": _sha(Path(__file__)),
        "rules_code_sha256": _sha(Path(__file__).with_name("triage_rules.py")),
        "group_code_sha256": _sha(Path(__file__).with_name("single_review.py")),
        "seed": SEED,
        "rule_version": RULE_VERSION,
        "groups": groups,
        "publisher_splits": parts,
        "rule_buckets": suggestions,
        "review_required": required,
        "counts": {
            "publisher_splits": {
                part: dict(Counter(rows[case_id]["source_label"] for case_id in ids))
                for part, ids in parts.items()
            },
            "rule_buckets": dict(Counter(suggestions.values())),
            "human_required": len(required),
            "train_rule_other_excluded": sum(
                suggestions[case_id] == "OTRO_CLARO"
                for case_id in parts["train"]
                if case_id in suggestions
            ),
        },
        "test_status": "SEALED_NOT_EVALUATED",
    }
    _exclusive(
        review_dir / "triage_manifest.json",
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    return {key: report[key] for key in ("status", "counts", "test_status")}


def freeze_triage(csv_path: Path, review_dir: Path) -> dict:
    selection, rows, digest = _selected_source(csv_path, review_dir)
    triage_path = review_dir / "triage_manifest.json"
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    if (
        triage.get("status") != "TRIAGE_REVIEW_PENDING"
        or triage.get("source_sha256") != selection["source_sha256"]
        or triage.get("selection_manifest_sha256") != _sha(review_dir / "selection_manifest.json")
        or triage.get("packet_sha256") != digest
        or triage.get("code_sha256") != _sha(Path(__file__))
        or triage.get("rules_code_sha256") != _sha(Path(__file__).with_name("triage_rules.py"))
        or triage.get("group_code_sha256") != _sha(Path(__file__).with_name("single_review.py"))
        or triage.get("groups") != _heuristic_groups(rows)
        or triage.get("publisher_splits") != _split_by_publisher(rows, triage["groups"])
    ):
        raise ValueError("Triage allocation or code has changed")
    expected_suggestions = {
        case_id: suggest(row["subject"], row["body"]).bucket
        for case_id, row in rows.items()
        if row["source_label"] == "1"
    }
    required = {
        case_id
        for part, ids in triage["publisher_splits"].items()
        for case_id in ids
        if rows[case_id]["source_label"] == "1"
        and (part != "train" or expected_suggestions[case_id] != "OTRO_CLARO")
    }
    if (
        triage.get("rule_buckets") != expected_suggestions
        or set(triage["review_required"]) != required
    ):
        raise ValueError("Rule buckets or required review list changed")
    decisions_path = review_dir / "single_annotations.jsonl"
    decisions = load_decisions(decisions_path, packet_sha256=digest)
    if not required <= decisions.keys():
        raise ValueError(f"Complete {len(required - decisions.keys())} required human reviews")
    if any(
        case_id not in rows
        or rows[case_id]["source_label"] != "1"
        or decision.content_sha256 != rows[case_id]["content_sha256"]
        for case_id, decision in decisions.items()
    ) or {item.reviewer_id for item in decisions.values()} != {"ADRIAN"}:
        raise ValueError("Reviewer, label or text fingerprint does not match")
    usable = {
        case_id: {**item, "label": "LEGITIMATE"}
        for case_id, item in rows.items()
        if item["source_label"] == "0"
    }
    usable.update(
        {
            case_id: {**rows[case_id], "label": "BEC"}
            for case_id, decision in decisions.items()
            if decision.label == "BEC"
        }
    )
    if sum(item["label"] == "BEC" for item in usable.values()) < 100:
        raise ValueError("Fewer than 100 human-confirmed synthetic BEC examples")
    parts = {
        part: sorted(case_id for case_id in ids if case_id in usable)
        for part, ids in triage["publisher_splits"].items()
    }
    counts = {
        part: Counter(usable[case_id]["label"] for case_id in ids) for part, ids in parts.items()
    }
    if any(
        counts[part]["BEC"] < minimum[0] or counts[part]["LEGITIMATE"] < minimum[1]
        for part, minimum in {
            "train": (40, 300),
            "validation": (10, 50),
            "test": (20, 100),
        }.items()
    ):
        raise ValueError("Insufficient human-confirmed BEC for a frozen train/validation/test")
    report = {
        "status": "SINGLE_ANNOTATOR_TRIAGE_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "source_sha256": selection["source_sha256"],
        "selection_manifest_sha256": _sha(review_dir / "selection_manifest.json"),
        "triage_manifest_sha256": _sha(triage_path),
        "packet_sha256": digest,
        "annotations_sha256": _sha(decisions_path),
        "reviewer_id": "ADRIAN",
        "code_sha256": _sha(Path(__file__).with_name("single_review.py")),
        "triage_code_sha256": _sha(Path(__file__)),
        "training_code_sha256": _sha(Path(__file__).with_name("single_review_training.py")),
        "seed": SEED,
        "annotation_method": "SINGLE_REVIEWER_ON_ALL_TEST_VALIDATION_AND_SELECTED_TRAIN",
        "benign_method": "PUBLISHER_SYNTHETIC_LABEL_0_NOT_REVIEWED",
        "group_method": "NORMALIZED_SUBJECT_OR_TEXT_TRIGRAM_JACCARD_085_HEURISTIC",
        "counts": {
            "BEC": sum(item["label"] == "BEC" for item in usable.values()),
            "LEGITIMATE": sum(item["label"] == "LEGITIMATE" for item in usable.values()),
            "OTHER_PHISHING_REVIEWED": sum(
                item.label == "OTHER_PHISHING" for item in decisions.values()
            ),
            "UNCERTAIN_REVIEWED": sum(item.label == "UNCERTAIN" for item in decisions.values()),
            "TRAIN_RULE_OTHER_EXCLUDED": len(
                [
                    case_id
                    for case_id in triage["publisher_splits"]["train"]
                    if rows[case_id]["source_label"] == "1" and case_id not in decisions
                ]
            ),
        },
        "groups": {case_id: triage["groups"][case_id] for case_id in usable},
        "splits": parts,
        "test_status": "SEALED_NOT_EVALUATED",
        "real_world_validity": "NOT_ESTABLISHED",
    }
    _exclusive(
        review_dir / "frozen_manifest.json",
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    return {key: report[key] for key in ("status", "counts", "test_status")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "freeze"))
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        prepare_triage(args.csv, args.review_dir)
        if args.operation == "prepare"
        else freeze_triage(args.csv, args.review_dir)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
