"""Pruebas del paquete sintético candidato; no son una evaluación científica."""

import json

from research.bec_training.generate_corpus import generate_candidates, generate_package


def test_generated_candidate_has_expected_distribution_and_opaque_ids():
    from research.bec_training.data import ResearchCase, split_groups, validate_cases

    records = generate_candidates()
    assert len(records) == 500
    assert {record["case_id"] for record in records} == {f"CASE-{i:04d}" for i in range(1, 501)}
    assert {record["group_id"] for record in records} == {f"GROUP-{i:04d}" for i in range(1, 251)}
    assert {record["source_id"] for record in records} == {f"SOURCE-{i:04d}" for i in range(1, 251)}
    assert sum(record["label"] == "BEC" for record in records) == 120
    assert sum(record["label"] == "LEGITIMATE" for record in records) == 380
    assert sum(record["is_hard_negative"] for record in records) == 100
    assert all("BEC" not in record["case_id"] for record in records)
    assert all(record["email"]["sender_email"].endswith(".example") for record in records)
    cases = [
        ResearchCase.model_validate({**record, "annotation_status": "ADJUDICATED"})
        for record in records
    ]
    validate_cases(cases)
    allocation = split_groups(cases)
    assert all(allocation.values())


def test_blind_packet_contains_no_labels_or_rationales(tmp_path):
    manifest = generate_package(tmp_path / "corpus")
    blind = [
        json.loads(line)
        for line in (tmp_path / "corpus" / "blind_review.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert manifest["status"] == "SYNTHETIC_CANDIDATE_REQUIRES_BLIND_REVIEW"
    assert len(blind) == 500
    assert all(
        set(row) == {"case_id", "group_id", "source_id", "annotation_status", "email"}
        for row in blind
    )
    assert all("label" not in row and "label_rationale" not in row for row in blind)
    assert all(row["annotation_status"] == "PENDING_BLIND_REVIEW" for row in blind)
