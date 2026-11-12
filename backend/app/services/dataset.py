"""Load the fixed synthetic corpus without network, database writes or classification."""

import re
from collections import Counter, defaultdict
from math import ceil
from pathlib import Path
from statistics import mean, median
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.schemas.dataset import DatasetCase

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[3] / "datasets" / "bec_eval.jsonl"
EXPECTED_SPLITS = {
    ("development", "LEGITIMATE"): 70,
    ("development", "BEC"): 28,
    ("holdout", "LEGITIMATE"): 30,
    ("holdout", "BEC"): 12,
}
EXPECTED_TYPES = {
    "EXECUTIVE_IMPERSONATION": 12,
    "VENDOR_FRAUD": 10,
    "BANK_ACCOUNT_CHANGE": 8,
    "SENSITIVE_DATA_REQUEST": 6,
    "OTHER": 4,
}


class DatasetValidationError(ValueError):
    """Content-free validation error suitable for CLI output."""


def validate_independence_groups(
    cases: list[DatasetCase], *, require_group_id: bool = False
) -> None:
    groups: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        if case.group_id is None:
            if require_group_id:
                raise DatasetValidationError(f"Missing independence group for {case.case_id}")
            continue
        groups[case.group_id].add(case.split.value)
    if any(len(splits) > 1 for splits in groups.values()):
        raise DatasetValidationError("Independence group crosses dataset splits")


def load_dataset(
    path: Path = DEFAULT_DATASET_PATH,
    *,
    validate_fixed: bool = True,
    require_group_id: bool = False,
) -> list[DatasetCase]:
    cases: list[DatasetCase] = []
    case_ids: set[str] = set()
    message_ids: set[str] = set()
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    case = DatasetCase.model_validate_json(line)
                except ValidationError:
                    raise DatasetValidationError(f"Invalid dataset row {line_number}") from None
                if case.case_id in case_ids or case.email.message_id in message_ids:
                    raise DatasetValidationError(f"Duplicate identity at row {line_number}")
                addresses = [
                    case.email.sender_email,
                    *case.email.to_recipients,
                    *case.email.cc_recipients,
                ]
                addresses += [
                    value for value in (case.email.reply_to, case.email.return_path) if value
                ]
                if any(
                    not value.rsplit("@", 1)[1].endswith((".example", ".test"))
                    for value in addresses
                ):
                    raise DatasetValidationError(f"Non-reserved address at row {line_number}")
                links = re.findall(
                    r"https?://[^\s<>\"']+",
                    case.email.subject + "\n" + case.email.body_text,
                    flags=re.I,
                )
                try:
                    hosts = [urlsplit(link).hostname or "" for link in links]
                except ValueError:
                    raise DatasetValidationError(
                        f"Invalid synthetic URL at row {line_number}"
                    ) from None
                if any(not host.endswith((".example", ".test")) for host in hosts):
                    raise DatasetValidationError(f"Non-reserved URL at row {line_number}")
                case_ids.add(case.case_id)
                message_ids.add(case.email.message_id)
                cases.append(case)
    except OSError, UnicodeError:
        raise DatasetValidationError("Dataset cannot be read as UTF-8") from None
    validate_independence_groups(cases, require_group_id=require_group_id)
    if not validate_fixed:
        return cases
    if Counter((case.split, case.label) for case in cases) != EXPECTED_SPLITS:
        raise DatasetValidationError(
            "Dataset must contain 140 cases with the approved label/split counts"
        )
    if Counter(case.expected_bec_type for case in cases if case.label == "BEC") != EXPECTED_TYPES:
        raise DatasetValidationError("Unexpected BEC type counts")
    if sum(case.is_hard_negative for case in cases) < 20:
        raise DatasetValidationError("Dataset must contain at least 20 legitimate hard negatives")
    return cases


def dataset_summary(cases: list[DatasetCase]) -> dict[str, object]:
    return {
        "total": len(cases),
        "labels": dict(Counter(case.label.value for case in cases)),
        "splits": dict(Counter(case.split.value for case in cases)),
        "bec_types": dict(
            Counter(case.expected_bec_type.value for case in cases if case.expected_bec_type)
        ),
        "hard_negatives": sum(case.is_hard_negative for case in cases),
    }


def _numeric_summary(values: list[int]) -> dict[str, int | float]:
    if not values:
        return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0}
    ordered = sorted(values)
    p95_index = max(0, ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(values),
        "min": ordered[0],
        "max": ordered[-1],
        "mean": round(mean(values), 2),
        "median": median(values),
        "p95": ordered[p95_index],
    }


def _text_length_summary(cases: list[DatasetCase], field: str) -> dict[str, object]:
    def values(selected: list[DatasetCase]) -> list[int]:
        return [len(getattr(case.email, field)) for case in selected]

    return {
        "overall": _numeric_summary(values(cases)),
        "by_label": {
            label: _numeric_summary(values([case for case in cases if case.label.value == label]))
            for label in ("LEGITIMATE", "BEC")
        },
    }


def dataset_descriptive_summary(cases: list[DatasetCase]) -> dict[str, object]:
    """Return aggregate development statistics without exposing email content or metadata."""
    development = [case for case in cases if case.split.value == "development"]
    missing_fields = (
        "thread_id",
        "sender_name",
        "reply_to",
        "return_path",
        "to_recipients",
        "cc_recipients",
        "subject",
        "body_text",
        "authentication_results",
    )

    def is_missing(value: object) -> bool:
        return value is None or value == "" or value == []

    missing = {
        field: {
            "count": sum(is_missing(getattr(case.email, field)) for case in development),
            "percentage": round(
                100
                * sum(is_missing(getattr(case.email, field)) for case in development)
                / len(development),
                2,
            ),
        }
        for field in missing_fields
    }
    return {
        "split": "development",
        "total": len(development),
        "labels": dict(Counter(case.label.value for case in development)),
        "bec_types": dict(
            Counter(
                case.expected_bec_type.value
                for case in development
                if case.expected_bec_type is not None
            )
        ),
        "hard_negatives": {
            "count": sum(case.is_hard_negative for case in development),
            "percentage": round(
                100 * sum(case.is_hard_negative for case in development) / len(development), 2
            ),
        },
        "text_lengths": {
            "subject": _text_length_summary(development, "subject"),
            "body_text": _text_length_summary(development, "body_text"),
            "subject_body": {
                "overall": _numeric_summary(
                    [len(case.email.subject) + len(case.email.body_text) for case in development]
                ),
                "by_label": {
                    label: _numeric_summary(
                        [
                            len(case.email.subject) + len(case.email.body_text)
                            for case in development
                            if case.label.value == label
                        ]
                    )
                    for label in ("LEGITIMATE", "BEC")
                },
            },
        },
        "missing_fields": missing,
    }
