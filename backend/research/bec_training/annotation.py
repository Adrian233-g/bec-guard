"""Revisión ciega offline y adjudicación, sin acceso a etiquetas generadas."""

import hashlib
import io
import json
import os
import random
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.dataset import DatasetLabel, ExpectedBECType
from app.schemas.email import EmailIngestRequest
from research.bec_training.data import ResearchDataError


class BlindReviewCase(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    case_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    group_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    source_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    annotation_status: Literal["PENDING_BLIND_REVIEW"]
    email: EmailIngestRequest


class ReviewAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    reviewer_id: str = Field(pattern=r"^[A-Z0-9_-]{3,32}$")
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    label: DatasetLabel
    expected_bec_type: ExpectedBECType | None = None
    is_hard_negative: bool = False
    rationale: str = Field(min_length=1, max_length=1000)
    reviewed_at: datetime

    @model_validator(mode="after")
    def check_label(self):
        if self.label == DatasetLabel.LEGITIMATE:
            if self.expected_bec_type is not None:
                raise ValueError("Legitimate annotation has invalid metadata")
        elif self.expected_bec_type is None or self.is_hard_negative:
            raise ValueError("BEC annotation requires a type and cannot be hard negative")
        return self


def packet_sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def load_blind_packet_bytes(contents: bytes) -> tuple[list[BlindReviewCase], str]:
    if not contents or len(contents) > 20_000_000:
        raise ResearchDataError("Blind review packet is empty or too large")
    cases: list[BlindReviewCase] = []
    seen: set[str] = set()
    try:
        for _number, row in enumerate(io.StringIO(contents.decode("utf-8")), 1):
            case = BlindReviewCase.model_validate_json(row)
            if case.case_id in seen:
                raise ResearchDataError("Duplicate case in blind review packet")
            seen.add(case.case_id)
            cases.append(case)
    except UnicodeError, ValidationError, ValueError:
        raise ResearchDataError("Invalid blind review packet") from None
    if not cases:
        raise ResearchDataError("Blind review packet is empty")
    return cases, packet_sha256(contents)


def reviewer_path(output_dir: Path, reviewer_id: str) -> Path:
    try:
        safe_id = ReviewAnnotation(
            reviewer_id=reviewer_id,
            packet_sha256="0" * 64,
            case_id="CASE-1",
            label=DatasetLabel.LEGITIMATE,
            rationale="validation",
            reviewed_at=datetime.now(UTC),
        ).reviewer_id
    except ValidationError:
        raise ResearchDataError("Invalid reviewer ID") from None
    return output_dir / f"annotations_{safe_id}.jsonl"


def _parse_annotations(
    rows: Iterable[str], *, reviewer_id: str, packet_hash: str
) -> dict[str, ReviewAnnotation]:
    annotations: dict[str, ReviewAnnotation] = {}
    try:
        for row in rows:
            annotation = ReviewAnnotation.model_validate_json(row)
            if annotation.reviewer_id != reviewer_id or annotation.packet_sha256 != packet_hash:
                raise ResearchDataError("Annotation file does not match reviewer or packet")
            if annotation.case_id in annotations:
                raise ResearchDataError("Duplicate annotation")
            annotations[annotation.case_id] = annotation
    except ValidationError, ValueError:
        raise ResearchDataError("Invalid annotation file") from None
    return annotations


def load_annotations(
    path: Path, *, reviewer_id: str, packet_hash: str
) -> dict[str, ReviewAnnotation]:
    if not path.exists():
        return {}
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except OSError, UnicodeError:
        raise ResearchDataError("Invalid annotation file") from None
    return _parse_annotations(rows, reviewer_id=reviewer_id, packet_hash=packet_hash)


def load_annotations_bytes(
    contents: bytes, *, reviewer_id: str, packet_hash: str
) -> dict[str, ReviewAnnotation]:
    try:
        rows = contents.decode("utf-8").splitlines()
    except UnicodeError:
        raise ResearchDataError("Invalid annotation file") from None
    return _parse_annotations(rows, reviewer_id=reviewer_id, packet_hash=packet_hash)


def save_annotation(path: Path, annotation: ReviewAnnotation) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_annotations(
        path, reviewer_id=annotation.reviewer_id, packet_hash=annotation.packet_sha256
    )
    current[annotation.case_id] = annotation
    content = "".join(
        json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for value in sorted(current.values(), key=lambda item: item.case_id)
    )
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def review_order(
    cases: Iterable[BlindReviewCase], *, reviewer_id: str, packet_hash: str
) -> list[str]:
    case_ids = [case.case_id for case in cases]
    random.Random(f"{packet_hash}:{reviewer_id}").shuffle(case_ids)
    return case_ids


def compare_reviewers(
    cases: list[BlindReviewCase],
    first: dict[str, ReviewAnnotation],
    second: dict[str, ReviewAnnotation],
    *,
    packet_hash: str,
) -> dict:
    expected = {case.case_id for case in cases}
    if not first or not second:
        raise ResearchDataError("Both reviewers must provide annotations")
    first_reviewer = next(iter(first.values())).reviewer_id
    second_reviewer = next(iter(second.values())).reviewer_id
    if first_reviewer == second_reviewer:
        raise ResearchDataError("Reviewers must have different IDs")
    if any(
        annotation.packet_sha256 != packet_hash
        for annotation in (*first.values(), *second.values())
    ):
        raise ResearchDataError("Annotation does not match packet")
    if not first.keys() <= expected or not second.keys() <= expected:
        raise ResearchDataError("Annotation contains an unknown case")
    complete = expected <= first.keys() and expected <= second.keys()
    disagreements = sorted(
        case_id
        for case_id in expected & first.keys() & second.keys()
        if (
            first[case_id].label != second[case_id].label
            or first[case_id].expected_bec_type != second[case_id].expected_bec_type
            or first[case_id].is_hard_negative != second[case_id].is_hard_negative
        )
    )
    return {
        "status": "READY_FOR_ADJUDICATION" if complete else "INCOMPLETE",
        "packet_sha256": packet_hash,
        "total_cases": len(expected),
        "reviewer_1_cases": len(first),
        "reviewer_2_cases": len(second),
        "agreements": len(expected & first.keys() & second.keys()) - len(disagreements),
        "disagreements": disagreements,
    }


def build_adjudicated_cases(
    cases: list[BlindReviewCase],
    first: dict[str, ReviewAnnotation],
    second: dict[str, ReviewAnnotation],
    adjudications: dict[str, ReviewAnnotation],
    *,
    packet_hash: str,
) -> list[dict]:
    summary = compare_reviewers(cases, first, second, packet_hash=packet_hash)
    if summary["status"] != "READY_FOR_ADJUDICATION":
        raise ResearchDataError("Both reviewers must complete the packet")
    expected = {case.case_id for case in cases}
    if set(adjudications) != set(summary["disagreements"]):
        raise ResearchDataError("Provide one adjudication for every disagreement only")
    first_by_id = first
    output: list[dict] = []
    for case in cases:
        left = first_by_id[case.case_id]
        decision = adjudications.get(case.case_id)
        if decision is None:
            decision = left
        elif decision.packet_sha256 != packet_hash:
            raise ResearchDataError("Adjudication does not match packet")
        if decision.case_id not in expected:
            raise ResearchDataError("Adjudication contains an unknown case")
        output.append(
            {
                "case_id": case.case_id,
                "group_id": case.group_id,
                "source_id": case.source_id,
                "label": decision.label.value,
                "expected_bec_type": (
                    decision.expected_bec_type.value if decision.expected_bec_type else None
                ),
                "is_hard_negative": decision.is_hard_negative,
                "label_rationale": decision.rationale,
                "annotation_status": "ADJUDICATED",
                "email": case.email.model_dump(mode="json"),
            }
        )
    return output
