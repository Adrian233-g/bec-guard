"""One-annotator labels stay blind, frozen and separate from an opened test."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.bec_training import single_review, single_review_training
from research.bec_training.single_review import Decision


def _letters(number: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    return "".join(letters[(number // (26**power)) % 26] for power in (2, 1, 0))


def _source() -> dict[str, dict]:
    rows = {}
    for index in range(1150):
        bec = index < 150
        subject = ("Invoice wire " if bec else "Team meeting ") + _letters(index)
        extra = " ".join(_letters((index * 17 + offset * 31) % 17576) for offset in range(8))
        body = (
            "CEO asks wire transfer account " if bec else "Regular project meeting notes "
        ) + extra
        key = single_review._text_key(f"{subject}\n{body}")
        rows[f"K{index + 1:06d}"] = {
            "subject": subject,
            "body": body,
            "source_label": "1" if bec else "0",
            "content_sha256": hashlib.sha256(key.encode()).hexdigest(),
        }
    return rows


def test_one_reviewer_freeze_and_single_opened_test(tmp_path, monkeypatch):
    source = _source()
    monkeypatch.setattr(single_review, "read_source", lambda _path: source)
    monkeypatch.setattr(single_review_training, "read_source", lambda _path: source)
    monkeypatch.setattr(single_review, "BENIGN_SAMPLE", 1000)
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("controlled-test-only", encoding="utf-8")
    review_dir = tmp_path / "review"
    single_review.prepare_packet(csv_path, review_dir, n_phish=150)
    packet, packet_hash = single_review.load_packet(review_dir / "blind_packet.jsonl")
    assert len(packet) == 150
    assert all("source_label" not in row and "prediction" not in row for row in packet)
    with pytest.raises(ValueError, match="Complete all"):
        single_review.freeze(csv_path, review_dir)

    annotations = [
        Decision(
            reviewer_id="OWNER_01",
            packet_sha256=packet_hash,
            case_id=row["case_id"],
            content_sha256=row["content_sha256"],
            label="BEC",
            bec_type="BANK_ACCOUNT_CHANGE",
            rationale="CEO requests an unauthorized payment.",
            reviewed_at=datetime.now(UTC),
        )
        for row in packet
    ]
    (review_dir / "single_annotations.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in annotations), encoding="utf-8"
    )
    frozen = single_review.freeze(csv_path, review_dir)
    assert frozen["counts"]["BEC"] == 150
    assert frozen["test_status"] == "SEALED_NOT_EVALUATED"
    with pytest.raises(ValueError, match="Frozen review"):
        single_review.save_decision(review_dir, annotations[0])

    model_dir = tmp_path / "model"
    report = single_review_training.train_v3(csv_path, review_dir, model_dir)
    assert report["status"] == "SINGLE_ANNOTATOR_SYNTHETIC_TRAINED_TEST_SEALED"
    assert report["test_status"] == "SEALED_NOT_EVALUATED"
    assert report["real_world_validity"] == "NOT_ESTABLISHED"
    assert report["assist_eligible"] is False
    assert "subject" not in json.dumps(report).lower()
    result = single_review_training.evaluate_test_once(
        csv_path, review_dir, model_dir, tmp_path / "locks", tmp_path / "test.json"
    )
    assert result["status"] == "SINGLE_ANNOTATOR_SYNTHETIC_FINAL_TEST"
    assert sum(result["confusion"][k] for k in ("tp", "fp", "tn", "fn")) == result["test_count"]
    assert result["assist_eligible"] is False
    with pytest.raises(FileExistsError):
        single_review_training.evaluate_test_once(
            csv_path, review_dir, model_dir, tmp_path / "locks", tmp_path / "other.json"
        )


def test_single_reviewer_app_starts_without_exposing_source_labels():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    entry = Path(__file__).resolve().parents[1] / "research" / "single_review_app.py"
    app = AppTest.from_file(str(entry), default_timeout=30).run()
    assert not app.exception
    assert "SINGLE_ANNOTATOR" not in str(app.session_state)


def test_single_reviewer_app_saves_a_blind_bec_decision(tmp_path):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    subject, body = "Business payment", "CEO asks for a wire transfer to a new account."
    fingerprint = hashlib.sha256(single_review._text_key(f"{subject}\n{body}").encode()).hexdigest()
    packet = (
        json.dumps(
            {
                "case_id": "K000001",
                "subject": subject,
                "body": body,
                "content_sha256": fingerprint,
            }
        )
        + "\n"
    ).encode()
    (tmp_path / "blind_packet.jsonl").write_bytes(packet)
    (tmp_path / "selection_manifest.json").write_text(
        json.dumps(
            {
                "status": "SINGLE_ANNOTATOR_SYNTHETIC_PENDING",
                "packet_sha256": hashlib.sha256(packet).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "triage_manifest.json").write_text(
        json.dumps(
            {
                "status": "TRIAGE_REVIEW_PENDING",
                "packet_sha256": hashlib.sha256(packet).hexdigest(),
                "review_required": ["K000001"],
                "publisher_splits": {"train": [], "validation": [], "test": ["K000001"]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "weak_train_manifest.json").write_text(
        json.dumps(
            {
                "status": "WEAK_TRAIN_HUMAN_EVAL_PENDING",
                "packet_sha256": hashlib.sha256(packet).hexdigest(),
                "triage_manifest_sha256": hashlib.sha256(
                    (tmp_path / "triage_manifest.json").read_bytes()
                ).hexdigest(),
                "review_required": ["K000001"],
            }
        ),
        encoding="utf-8",
    )
    entry = Path(__file__).resolve().parents[1] / "research" / "single_review_app.py"
    app = AppTest.from_file(str(entry), default_timeout=30).run()
    app.get_by_key("review_dir").set_value(str(tmp_path)).run()
    app.button(key="load_packet").click().run()
    assert not app.exception
    assert app.session_state["order"] == ["K000001"]
    assert app.session_state["weak"]["status"] == "WEAK_TRAIN_HUMAN_EVAL_PENDING"
    assert any("Fundamento científico" in item.label for item in app.expander)
    assert not any("Filtro automático" in str(item.value) for item in app.info)
    app.get_by_key("label_K000001").set_value("BEC · fraude empresarial").run()
    app.get_by_key("type_K000001").set_value("Cambio de cuenta bancaria").run()
    app.get_by_key("rationale_K000001").set_value("Solicitud de pago y cambio de cuenta.").run()
    app.button(key="save_review").click().run()
    assert not app.exception
    decisions = single_review.load_decisions(
        tmp_path / "single_annotations.jsonl", packet_sha256=hashlib.sha256(packet).hexdigest()
    )
    assert decisions["K000001"].label == "BEC"
    assert decisions["K000001"].reviewer_id == "ADRIAN"
