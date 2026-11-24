"""Rule drafts are never attributed to ADRIAN or counted as test truth."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from research.bec_training import (
    ai_drafts,
    single_review,
    single_review_training,
    triage_workflow,
    weak_supervision,
)
from research.bec_training.single_review import Decision
from research.bec_training.triage_rules import suggest


def _letters(number: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    return "".join(letters[(number // (26**power)) % 26] for power in (2, 1, 0))


def _source() -> dict[str, dict]:
    result = {}
    for index in range(3000):
        subtype = "BEC" if index < 300 else ("PHISHING" if index < 2000 else "LEGITIMATE")
        subject = f"{subtype} {_letters(index)}"
        extra = " ".join(_letters((index * 17 + offset * 31) % 17576) for offset in range(8))
        body = {
            "BEC": "CEO asks you to process a confidential wire transfer to our company ",
            "PHISHING": "Please verify your identity for your personal account via [URL] ",
            "LEGITIMATE": "Team meeting notes about routine project planning ",
        }[subtype] + extra
        digest = hashlib.sha256(single_review._text_key(f"{subject}\n{body}").encode()).hexdigest()
        result[f"K{index + 1:06d}"] = {
            "subject": subject,
            "body": body,
            "source_label": "0" if subtype == "LEGITIMATE" else "1",
            "content_sha256": digest,
        }
    return result


def test_triage_suggestions_are_explanations_not_bec_ground_truth():
    assert (
        suggest(
            "Urgent wire transfer request",
            "I am the CEO. Process a confidential wire transfer for our company.",
        ).bucket
        == "POSIBLE_BEC"
    )
    assert (
        suggest(
            "Confirm your identity",
            "Secure your account via [URL] or it will be locked.",
        ).bucket
        == "OTRO_CLARO"
    )
    assert suggest("Important message", "Please review the attached details.").bucket == "DUDOSO"
    assert suggest("Crypto wallet", "Send the wallet details to me.").bucket == "DUDOSO"
    assert (
        suggest("Company gift card", "Please review this gift card for our company.").bucket
        == "DUDOSO"
    )


def test_triage_never_uses_rule_other_as_bec_ground_truth(tmp_path, monkeypatch):
    source = _source()
    for module in (single_review, triage_workflow, single_review_training):
        monkeypatch.setattr(module, "read_source", lambda _path: source)
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("toy source", encoding="utf-8")
    directory = tmp_path / "review"
    single_review.prepare_packet(csv_path, directory, n_phish=2000)
    summary = triage_workflow.prepare_triage(csv_path, directory)
    assert summary["counts"]["train_rule_other_excluded"] > 500
    triage = json.loads((directory / "triage_manifest.json").read_text(encoding="utf-8"))
    assert set(triage["publisher_splits"]["test"]) & set(triage["review_required"])
    skipped = {
        case_id
        for case_id in triage["publisher_splits"]["train"]
        if source[case_id]["source_label"] == "1" and case_id not in triage["review_required"]
    }
    assert skipped and all(source[case_id]["source_label"] == "1" for case_id in skipped)
    with pytest.raises(ValueError, match="required human reviews"):
        triage_workflow.freeze_triage(csv_path, directory)

    packet, packet_hash = single_review.load_packet(directory / "blind_packet.jsonl")
    by_id = {row["case_id"]: row for row in packet}
    decisions = []
    for case_id in triage["review_required"]:
        is_bec = int(case_id[1:]) <= 300
        decisions.append(
            Decision(
                reviewer_id="ADRIAN",
                packet_sha256=packet_hash,
                case_id=case_id,
                content_sha256=by_id[case_id]["content_sha256"],
                label="BEC" if is_bec else "OTHER_PHISHING",
                bec_type="BANK_ACCOUNT_CHANGE" if is_bec else None,
                rationale="Test fixture BEC request" if is_bec else "Test fixture other phishing",
                reviewed_at=datetime.now(UTC),
            )
        )
    (directory / "single_annotations.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in decisions), encoding="utf-8"
    )
    frozen = triage_workflow.freeze_triage(csv_path, directory)
    assert frozen["counts"]["TRAIN_RULE_OTHER_EXCLUDED"] == len(skipped)
    assert frozen["counts"]["BEC"] >= 100
    assert frozen["test_status"] == "SEALED_NOT_EVALUATED"
    report = single_review_training.train_v3(csv_path, directory, tmp_path / "model")
    assert report["test_status"] == "SEALED_NOT_EVALUATED"
    assert report["status"] == "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED"
    result = single_review_training.evaluate_test_once(
        csv_path, directory, tmp_path / "model", tmp_path / "locks", tmp_path / "test.json"
    )
    assert result["status"] == "SINGLE_ANNOTATOR_SYNTHETIC_FINAL_TEST"
    assert sum(result["confusion"][key] for key in ("tp", "fp", "tn", "fn")) == result["test_count"]
    with pytest.raises(FileExistsError):
        single_review_training.evaluate_test_once(
            csv_path, directory, tmp_path / "model", tmp_path / "locks", tmp_path / "again.json"
        )


def test_weak_training_uses_rule_only_in_train_and_human_truth_in_test(tmp_path, monkeypatch):
    source = _source()
    for module in (single_review, triage_workflow, single_review_training):
        monkeypatch.setattr(module, "read_source", lambda _path: source)
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("toy source", encoding="utf-8")
    directory = tmp_path / "review"
    single_review.prepare_packet(csv_path, directory, n_phish=2000)
    triage_workflow.prepare_triage(csv_path, directory)
    ai_drafts.build_drafts(directory, directory / "ai_drafts.json")
    drafts = json.loads((directory / "ai_drafts.json").read_text(encoding="utf-8"))
    triage = json.loads((directory / "triage_manifest.json").read_text(encoding="utf-8"))
    assert set(drafts["proposals"]) <= set(triage["publisher_splits"]["train"])
    assert not set(drafts["proposals"]) & set(triage["publisher_splits"]["test"])
    summary = weak_supervision.prepare_weak(csv_path, directory)
    assert summary["counts"]["human_validation"] >= 250
    assert summary["counts"]["human_test"] >= 250
    assert summary["counts"]["weak_train_bec"] >= 40
    assert summary["counts"]["train_other_phishing_not_used"] > 1000
    weak = json.loads((directory / "weak_train_manifest.json").read_text(encoding="utf-8"))
    assert all(case_id in triage["publisher_splits"]["train"] for case_id in weak["weak_train_bec"])
    assert all(
        case_id in triage["publisher_splits"]["validation"] + triage["publisher_splits"]["test"]
        for case_id in weak["review_required"]
    )
    with pytest.raises(ValueError, match="human evaluation labels"):
        weak_supervision.freeze_weak(csv_path, directory)

    packet, packet_hash = single_review.load_packet(directory / "blind_packet.jsonl")
    by_id = {row["case_id"]: row for row in packet}
    decisions = []
    for case_id in weak["review_required"]:
        is_bec = int(case_id[1:]) <= 300
        decisions.append(
            Decision(
                reviewer_id="ADRIAN",
                packet_sha256=packet_hash,
                case_id=case_id,
                content_sha256=by_id[case_id]["content_sha256"],
                label="BEC" if is_bec else "OTHER_PHISHING",
                bec_type="BANK_ACCOUNT_CHANGE" if is_bec else None,
                rationale="Test fixture BEC" if is_bec else "Test fixture other phishing",
                reviewed_at=datetime.now(UTC),
            )
        )
    (directory / "single_annotations.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in decisions), encoding="utf-8"
    )
    frozen = weak_supervision.freeze_weak(csv_path, directory)
    assert frozen["label_sources"]["weak_train_BEC"] == len(weak["weak_train_bec"])
    assert frozen["label_sources"]["human_test_BEC"] >= 20
    assert frozen["status"] == "SINGLE_ANNOTATOR_WEAK_TRAIN_FROZEN"
    report = single_review_training.train_v3(csv_path, directory, tmp_path / "model")
    assert report["status"] == "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED"
    assert report["review_method"] == "WEAK_RULE_TRAIN_BEC_HUMAN_VALIDATION_TEST"
    assert report["test_status"] == "SEALED_NOT_EVALUATED"
    result = single_review_training.evaluate_test_once(
        csv_path, directory, tmp_path / "model", tmp_path / "locks", tmp_path / "test.json"
    )
    assert result["annotation_method"] == "WEAK_RULE_TRAIN_BEC_HUMAN_VALIDATION_TEST"
    assert result["test_count"] == sum(result["confusion"][key] for key in ("tp", "fp", "tn", "fn"))
    with pytest.raises(FileExistsError):
        single_review_training.evaluate_test_once(
            csv_path, directory, tmp_path / "model", tmp_path / "locks", tmp_path / "again.json"
        )
