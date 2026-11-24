"""Pruebas de revisión ciega; no generan resultados de detección."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.bec_training.annotation import (
    ReviewAnnotation,
    build_adjudicated_cases,
    compare_reviewers,
    load_annotations,
    load_annotations_bytes,
    load_blind_packet_bytes,
    reviewer_path,
    save_annotation,
)
from research.bec_training.data import ResearchDataError
from research.bec_training.generate_corpus import generate_candidates


def _blind_bytes():
    return b"".join(
        (
            json.dumps(
                {
                    "case_id": record["case_id"],
                    "group_id": record["group_id"],
                    "source_id": record["source_id"],
                    "annotation_status": "PENDING_BLIND_REVIEW",
                    "email": record["email"],
                }
            )
            + "\n"
        ).encode()
        for record in generate_candidates()[:4]
    )


def _annotation(case_id, packet_hash, reviewer, label="LEGITIMATE", bec_type=None):
    return ReviewAnnotation(
        reviewer_id=reviewer,
        packet_sha256=packet_hash,
        case_id=case_id,
        label=label,
        expected_bec_type=bec_type,
        rationale="Revisión independiente del caso.",
        reviewed_at=datetime.now(UTC),
    )


def test_annotations_are_private_per_reviewer_and_packet_bound(tmp_path):
    contents = _blind_bytes()
    cases, packet_hash = load_blind_packet_bytes(contents)
    path = reviewer_path(tmp_path, "REVIEWER_A")
    save_annotation(path, _annotation(cases[0].case_id, packet_hash, "REVIEWER_A"))
    loaded = load_annotations(path, reviewer_id="REVIEWER_A", packet_hash=packet_hash)
    assert set(loaded) == {cases[0].case_id}
    with pytest.raises(ResearchDataError):
        load_annotations(path, reviewer_id="REVIEWER_B", packet_hash=packet_hash)


def test_disagreement_requires_explicit_adjudication():
    cases, packet_hash = load_blind_packet_bytes(_blind_bytes())
    first = {case.case_id: _annotation(case.case_id, packet_hash, "REVIEWER_A") for case in cases}
    second = {case.case_id: _annotation(case.case_id, packet_hash, "REVIEWER_B") for case in cases}
    second[cases[0].case_id] = _annotation(
        cases[0].case_id,
        packet_hash,
        "REVIEWER_B",
        label="BEC",
        bec_type="BANK_ACCOUNT_CHANGE",
    )
    summary = compare_reviewers(cases, first, second, packet_hash=packet_hash)
    assert summary["status"] == "READY_FOR_ADJUDICATION"
    assert summary["disagreements"] == [cases[0].case_id]
    with pytest.raises(ResearchDataError):
        build_adjudicated_cases(cases, first, second, {}, packet_hash=packet_hash)


def test_complete_reviews_produce_pipeline_ready_adjudicated_cases():
    contents = _blind_bytes()
    cases, packet_hash = load_blind_packet_bytes(contents)
    first = {case.case_id: _annotation(case.case_id, packet_hash, "REVIEWER_A") for case in cases}
    second_jsonl = "".join(
        json.dumps(annotation.model_dump(mode="json")) + "\n"
        for annotation in (_annotation(case.case_id, packet_hash, "REVIEWER_B") for case in cases)
    ).encode()
    second = load_annotations_bytes(second_jsonl, reviewer_id="REVIEWER_B", packet_hash=packet_hash)
    result = build_adjudicated_cases(cases, first, second, {}, packet_hash=packet_hash)
    assert len(result) == len(cases)
    assert all(row["annotation_status"] == "ADJUDICATED" for row in result)


def test_annotation_and_adjudication_apps_start_offline():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[1] / "research"
    for name in ("annotation_app.py", "adjudication_app.py"):
        app = AppTest.from_file(str(root / name), default_timeout=30).run()
        assert not app.exception
