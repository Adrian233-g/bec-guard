"""Cohorte sintética BEC de un evaluador: paquete ciego, etiquetas y freeze.

No convierte phishing genérico en BEC ni afirma adjudicación por dos personas.
Los cuerpos solo viven en el CSV externo y el paquete local ignorado por Git.
"""

import argparse
import csv
import hashlib
import json
import os
import random
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.dataset import ExpectedBECType
from research.bec_training.auxiliary_phishing_benchmark import MEMBER_SHA256, _text_key
from research.bec_training.data import _shingles
from research.bec_training.external_benchmark import _sha

SEED = 20261121
PHISHING_SAMPLE = 2000
BENIGN_SAMPLE = 1000


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    reviewer_id: str = Field(pattern=r"^[A-Z0-9_-]{3,32}$")
    packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(pattern=r"^K[0-9]{6}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    label: Literal["BEC", "OTHER_PHISHING", "UNCERTAIN"]
    bec_type: ExpectedBECType | None = None
    rationale: str = Field(min_length=4, max_length=500)
    reviewed_at: AwareDatetime

    @model_validator(mode="after")
    def consistent(self):
        if (self.label == "BEC") != (self.bec_type is not None):
            raise ValueError("BEC needs a type; other decisions cannot have one")
        return self


def read_source(path: Path) -> dict[str, dict]:
    if _sha(path) != MEMBER_SHA256:
        raise ValueError("Source CSV differs from the inspected 60k-row release")
    csv.field_size_limit(10**8)
    cases = {}
    unique: dict[str, str] = {}
    counts: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["Subject", "Body", "Label"]:
            raise ValueError("Unexpected source columns")
        for index, row in enumerate(reader, 1):
            label = row["Label"]
            counts[label] += 1
            if (
                label not in {"0", "1"}
                or not (row["Subject"] or "").strip()
                or not (row["Body"] or "").strip()
            ):
                raise ValueError("Invalid source label or empty text")
            subject, body = row["Subject"].strip(), row["Body"].strip()
            digest = hashlib.sha256(_text_key(f"{subject}\n{body}").encode()).hexdigest()
            if digest in unique:
                if unique[digest] != label:
                    raise ValueError("Duplicate source text has conflicting labels")
                continue
            unique[digest] = label
            cases[f"K{index:06d}"] = {
                "subject": subject,
                "body": body,
                "source_label": label,
                "content_sha256": digest,
            }
    if dict(counts) != {"0": 29806, "1": 30194}:
        raise ValueError("Publisher label counts changed")
    return cases


def sampled_ids(cases: dict[str, dict], *, n_phish: int, n_benign: int) -> dict[str, list[str]]:
    randomizer = random.Random(SEED)
    pools = {
        label: sorted(case_id for case_id, case in cases.items() if case["source_label"] == label)
        for label in ("0", "1")
    }
    if n_phish > len(pools["1"]) or n_benign > len(pools["0"]) or min(n_phish, n_benign) < 1:
        raise ValueError("Requested sample exceeds the unique source population")
    return {
        "1": sorted(randomizer.sample(pools["1"], n_phish)),
        "0": sorted(randomizer.sample(pools["0"], n_benign)),
    }


def _exclusive(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)


def prepare_packet(csv_path: Path, out: Path, *, n_phish: int = PHISHING_SAMPLE) -> dict:
    cases = read_source(csv_path)
    selected = sampled_ids(cases, n_phish=n_phish, n_benign=BENIGN_SAMPLE)
    packet_rows = [
        {
            "case_id": case_id,
            "subject": cases[case_id]["subject"],
            "body": cases[case_id]["body"],
            "content_sha256": cases[case_id]["content_sha256"],
        }
        for case_id in selected["1"]
    ]
    random.Random(SEED).shuffle(packet_rows)
    packet = ("\n".join(json.dumps(row, ensure_ascii=False) for row in packet_rows) + "\n").encode()
    manifest = {
        "status": "SINGLE_ANNOTATOR_SYNTHETIC_PENDING",
        "source_sha256": _sha(csv_path),
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "selection_code_sha256": _sha(Path(__file__)),
        "seed": SEED,
        "publisher_labels": {"0": "SYNTHETIC_BENIGN", "1": "GENERIC_PHISHING"},
        "phishing_to_annotate": len(selected["1"]),
        "publisher_benign": len(selected["0"]),
        "selected": [
            {
                "case_id": case_id,
                "source_label": label,
                "content_sha256": cases[case_id]["content_sha256"],
            }
            for label in ("0", "1")
            for case_id in selected[label]
        ],
    }
    out.mkdir(parents=True, exist_ok=False)
    _exclusive(out / "blind_packet.jsonl", packet)
    _exclusive(out / "selection_manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return {
        key: manifest[key]
        for key in ("status", "packet_sha256", "phishing_to_annotate", "publisher_benign")
    }


def load_packet(path: Path) -> tuple[list[dict], str]:
    payload = path.read_bytes()
    if not payload or len(payload) > 20_000_000:
        raise ValueError("Review packet is empty or too large")
    rows = [json.loads(line) for line in payload.splitlines()]
    ids = [row["case_id"] for row in rows]
    if len(set(ids)) != len(ids) or any(
        set(row) != {"case_id", "subject", "body", "content_sha256"}
        or not re.fullmatch(r"K[0-9]{6}", row["case_id"])
        or hashlib.sha256(_text_key(f"{row['subject']}\n{row['body']}").encode()).hexdigest()
        != row["content_sha256"]
        for row in rows
    ):
        raise ValueError("Invalid or changed review packet")
    return rows, hashlib.sha256(payload).hexdigest()


def load_decisions(path: Path, *, packet_sha256: str) -> dict[str, Decision]:
    if not path.is_file():
        return {}
    decisions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        decision = Decision.model_validate_json(line)
        if decision.packet_sha256 != packet_sha256 or decision.case_id in decisions:
            raise ValueError("Annotations do not match this packet or contain duplicate cases")
        decisions[decision.case_id] = decision
    return decisions


def save_decision(out: Path, decision: Decision) -> None:
    if (out / "frozen_manifest.json").exists():
        raise ValueError("Frozen review cannot be modified")
    packet, packet_sha = load_packet(out / "blind_packet.jsonl")
    if packet_sha != decision.packet_sha256 or decision.case_id not in {
        row["case_id"] for row in packet
    }:
        raise ValueError("Annotation belongs to a different packet")
    case = next(row for row in packet if row["case_id"] == decision.case_id)
    if case["content_sha256"] != decision.content_sha256:
        raise ValueError("Annotation text fingerprint does not match")
    path = out / "single_annotations.jsonl"
    current = load_decisions(path, packet_sha256=packet_sha)
    if current and next(iter(current.values())).reviewer_id != decision.reviewer_id:
        raise ValueError("A second reviewer cannot be mixed into this file")
    current[decision.case_id] = decision
    contents = "".join(
        row.model_dump_json() + "\n" for row in sorted(current.values(), key=lambda r: r.case_id)
    )
    temporary = out / "single_annotations.tmp"
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _heuristic_groups(rows: dict[str, dict]) -> dict[str, str]:
    """Connect identical subject templates and >=0.85 text-trigram similarity."""
    ids = sorted(rows)
    parent = {case_id: case_id for case_id in ids}

    def root(case_id: str) -> str:
        while parent[case_id] != case_id:
            parent[case_id] = parent[parent[case_id]]
            case_id = parent[case_id]
        return case_id

    def join(left: str, right: str) -> None:
        a, b = root(left), root(right)
        parent[max(a, b)] = min(a, b)

    subjects = {}
    shingles = {}
    index: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for case_id in ids:
        case = rows[case_id]
        subject = re.sub(r"\d+", "#", _text_key(case["subject"]))
        if subject:
            other = subjects.setdefault(subject, case_id)
            join(case_id, other)
        signature = _shingles(case["subject"] + " " + case["body"])
        candidates = set().union(*(index[item] for item in signature)) if signature else set()
        for other in candidates:
            previous = shingles[other]
            if len(signature & previous) / len(signature | previous) >= 0.85:
                join(case_id, other)
        shingles[case_id] = signature
        for item in signature:
            index[item].add(case_id)
    return {case_id: f"G{root(case_id)}" for case_id in ids}


def _allocate(rows: dict[str, dict], groups: dict[str, str]) -> dict[str, list[str]]:
    from sklearn.model_selection import GroupShuffleSplit

    ids = sorted(rows)
    y = [int(rows[case_id]["label"] == "BEC") for case_id in ids]
    group_ids = [groups[case_id] for case_id in ids]
    best = None
    for attempt in range(128):
        outer = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED + attempt)
        development, test = next(outer.split(ids, y, group_ids))
        dev_ids = [ids[index] for index in development]
        inner = GroupShuffleSplit(n_splits=1, test_size=0.17647, random_state=SEED + attempt)
        train, validation = next(
            inner.split(
                dev_ids,
                [int(rows[case_id]["label"] == "BEC") for case_id in dev_ids],
                [groups[case_id] for case_id in dev_ids],
            )
        )
        parts = {
            "train": sorted(dev_ids[index] for index in train),
            "validation": sorted(dev_ids[index] for index in validation),
            "test": sorted(ids[index] for index in test),
        }
        counts = {
            part: Counter(rows[case_id]["label"] for case_id in selected)
            for part, selected in parts.items()
        }
        if any(
            counts[part]["BEC"] < minimum[0] or counts[part]["LEGITIMATE"] < minimum[1]
            for part, minimum in {
                "train": (40, 300),
                "validation": (10, 50),
                "test": (20, 100),
            }.items()
        ):
            continue
        score = sum(
            abs(len(parts[part]) / len(ids) - fraction)
            for part, fraction in (("train", 0.7), ("validation", 0.15), ("test", 0.15))
        )
        if best is None or score < best[0]:
            best = (score, parts)
    if best is None:
        raise ValueError("Insufficient independent BEC/benign groups for a frozen test")
    return best[1]


def freeze(csv_path: Path, out: Path) -> dict:
    source = read_source(csv_path)
    manifest_path = out / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "SINGLE_ANNOTATOR_SYNTHETIC_PENDING"
        or manifest.get("source_sha256") != _sha(csv_path)
        or manifest.get("seed") != SEED
        or manifest.get("selection_code_sha256") != _sha(Path(__file__))
    ):
        raise ValueError("Selection provenance changed")
    selection = sampled_ids(
        source,
        n_phish=manifest["phishing_to_annotate"],
        n_benign=manifest["publisher_benign"],
    )
    if manifest["selected"] != [
        {
            "case_id": case_id,
            "source_label": label,
            "content_sha256": source[case_id]["content_sha256"],
        }
        for label in ("0", "1")
        for case_id in selection[label]
    ]:
        raise ValueError("Selection manifest is not reproducible")
    packet, digest = load_packet(out / "blind_packet.jsonl")
    if (
        digest != manifest["packet_sha256"]
        or {row["case_id"] for row in packet} != set(selection["1"])
        or any(row["content_sha256"] != source[row["case_id"]]["content_sha256"] for row in packet)
    ):
        raise ValueError("Blind packet differs from the selected sample")
    decisions_path = out / "single_annotations.jsonl"
    decisions = load_decisions(decisions_path, packet_sha256=digest)
    if set(decisions) != set(selection["1"]):
        raise ValueError(f"Complete all {len(selection['1'])} blinded annotations before freeze")
    if len({row.reviewer_id for row in decisions.values()}) != 1 or any(
        row.content_sha256 != source[row.case_id]["content_sha256"] for row in decisions.values()
    ):
        raise ValueError("Annotation identity or content fingerprint changed")
    usable = {case_id: {**source[case_id], "label": "LEGITIMATE"} for case_id in selection["0"]}
    usable.update(
        {
            case_id: {**source[case_id], "label": "BEC"}
            for case_id, decision in decisions.items()
            if decision.label == "BEC"
        }
    )
    if len([row for row in usable.values() if row["label"] == "BEC"]) < 100:
        raise ValueError("Fewer than 100 single-reviewed synthetic BEC examples")
    groups = _heuristic_groups(usable)
    allocation = _allocate(usable, groups)
    report = {
        "status": "SINGLE_ANNOTATOR_SYNTHETIC_FROZEN",
        "created_at": datetime.now(UTC).isoformat(),
        "source_sha256": manifest["source_sha256"],
        "packet_sha256": digest,
        "selection_manifest_sha256": _sha(manifest_path),
        "annotations_sha256": _sha(decisions_path),
        "reviewer_id": next(iter(decisions.values())).reviewer_id,
        "code_sha256": _sha(Path(__file__)),
        "training_code_sha256": _sha(Path(__file__).with_name("single_review_training.py")),
        "seed": SEED,
        "annotation_method": "SINGLE_REVIEWER_NOT_ADJUDICATED",
        "benign_method": "PUBLISHER_SYNTHETIC_LABEL_0_NOT_REVIEWED",
        "group_method": "NORMALIZED_SUBJECT_OR_TEXT_TRIGRAM_JACCARD_085_HEURISTIC",
        "counts": {
            "BEC": sum(row["label"] == "BEC" for row in usable.values()),
            "LEGITIMATE": sum(row["label"] == "LEGITIMATE" for row in usable.values()),
            "OTHER_PHISHING_EXCLUDED": sum(r.label == "OTHER_PHISHING" for r in decisions.values()),
            "UNCERTAIN_EXCLUDED": sum(r.label == "UNCERTAIN" for r in decisions.values()),
        },
        "groups": groups,
        "splits": allocation,
        "test_status": "SEALED_NOT_EVALUATED",
        "real_world_validity": "NOT_ESTABLISHED",
    }
    _exclusive(
        out / "frozen_manifest.json",
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    return {key: report[key] for key in ("status", "counts", "test_status")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "freeze"))
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        prepare_packet(args.csv, args.output_dir)
        if args.operation == "prepare"
        else freeze(args.csv, args.output_dir)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
