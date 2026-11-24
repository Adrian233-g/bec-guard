"""Flujo visible del laboratorio sin servicios externos."""

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("sklearn")
from streamlit.testing.v1 import AppTest


def test_offline_app_demo_load_train_compare_export():
    entry = Path(__file__).resolve().parents[1] / "research" / "streamlit_app.py"
    at = AppTest.from_file(str(entry), default_timeout=30).run()
    assert not at.exception
    at.get_by_key("vista").set_value("Metodología").run()
    assert not at.exception
    at.get_by_key("vista").set_value("Datos").run()
    at.button(key="demo").click().run()
    assert not at.exception
    assert at.session_state["manifest"]["status"] == "TECHNICAL_FIXTURE_ONLY"
    at.get_by_key("vista").set_value("Entrenamiento").run()
    at.button(key="train").click().run(timeout=30)
    assert not at.exception
    assert at.session_state["training"]["test_status"] == "NOT_RUN"
    assert (
        hashlib.sha256(at.session_state["training_model_bytes"]).hexdigest()
        == (at.session_state["training"]["model_sha256"])
    )
    at.get_by_key("vista").set_value("Comparación").run()
    at.button(key="compare").click().run()
    assert not at.exception
    assert at.session_state["comparison"]["conditions"]["C3"]["status"] == "NOT_RUN"
    at.get_by_key("vista").set_value("Estadística").run()
    assert not at.exception
    assert at.session_state["comparison_raw"] is not None
    at.get_by_key("vista").set_value("Metodología").run()
    assert not at.exception
    at.get_by_key("vista").set_value("Informe").run()
    assert not at.exception
    assert at.session_state["comparison"]["status"] == "TECHNICAL_FIXTURE_ONLY"


def test_authorized_input_and_cached_semantics_remain_offline():
    from research.bec_training.demo import demo_cases

    rows = [case.model_dump(mode="json") for case in demo_cases()]
    rows[0]["email"]["sender_email"] = "persona@empresa.org"
    dataset = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    context = json.dumps(
        {
            "executives": [
                {"name": "Nora Prisma", "position": "Directora", "email": "nora@empresa.org"}
            ],
            "vendors": [],
        }
    ).encode()
    cache = json.dumps(
        {
            "metadata": {
                "provider": "mock",
                "model": "schema-v1",
                "prompt_version": "semantic-v2",
                "dataset_sha256": hashlib.sha256(dataset).hexdigest(),
                "context_sha256": hashlib.sha256(context).hexdigest(),
            },
            "scores": {row["case_id"]: 50 for row in rows},
        }
    ).encode()
    entry = Path(__file__).resolve().parents[1] / "research" / "streamlit_app.py"
    at = AppTest.from_file(str(entry), default_timeout=30).run()
    at.get_by_key("vista").set_value("Datos").run()
    at.get_by_key("kind").set_value("Autorizado").run()
    at.get_by_key("permission").set_value("PERM_001").run()
    at.get_by_key("role").set_value("Evaluación independiente").run()
    at.file_uploader(key="dataset").upload("nuevo.jsonl", dataset).run()
    at.button(key="load").click().run()
    assert not at.exception
    assert at.session_state["manifest"]["status"] == "AUTHORIZED_CORPUS_UNVERIFIED"
    assert set(at.session_state["manifest"]["splits"]) == {"evaluation"}
    at.file_uploader(key="context_file").upload("contexto.json", context).run()
    at.button(key="load_context").click().run()
    at.get_by_key("vista").set_value("Comparación").run()
    at.file_uploader(key="semantic_cache").upload("scores.json", cache).run()
    at.button(key="compare").click().run()
    assert not at.exception
    assert at.session_state["comparison"]["semantic_source"] == "CACHED_AUTHORIZED"
    assert at.session_state["comparison"]["conditions"]["C3"]["total"] == len(rows)
    assert at.session_state["comparison"]["conditions"]["C4"]["status"] == "NOT_RUN"
    assert at.session_state["comparison"]["scientific_inference"].startswith("DESCRIPTIVE_ONLY")


def test_authorized_test_has_session_guard_after_frozen_selection(tmp_path, monkeypatch):
    from research.bec_training.demo import demo_cases

    monkeypatch.setenv("BEC_RESEARCH_TEST_LOCK_DIR", str(tmp_path / "test-locks"))
    rows = [case.model_dump(mode="json") for case in demo_cases()]
    rows[0]["email"]["sender_email"] = "persona@empresa.org"
    dataset = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    entry = Path(__file__).resolve().parents[1] / "research" / "streamlit_app.py"
    at = AppTest.from_file(str(entry), default_timeout=30).run()
    at.get_by_key("vista").set_value("Datos").run()
    at.get_by_key("kind").set_value("Autorizado").run()
    at.get_by_key("permission").set_value("PERM_001").run()
    at.file_uploader(key="dataset").upload("nuevo.jsonl", dataset).run()
    at.button(key="load").click().run()
    at.get_by_key("vista").set_value("Entrenamiento").run()
    at.checkbox(key="evaluate_test").check().run()
    at.button(key="train").click().run(timeout=30)
    assert not at.exception
    report = at.session_state["training"]
    assert report["test_status"] == "AUTHORIZED_TEST_EVALUATED"
    assert (
        hashlib.sha256(at.session_state["training_model_bytes"]).hexdigest()
        == (report["model_sha256"])
    )
    assert len(report["selection_frozen_sha256"]) == 64
    assert report["dataset_sha256"] in at.session_state["final_test_hashes"]
    at.run()
    assert at.button(key="train").disabled


def test_statistics_view_prepares_hypothetical_demo():
    entry = Path(__file__).resolve().parents[1] / "research" / "streamlit_app.py"
    at = AppTest.from_file(str(entry), default_timeout=60).run()
    assert not at.exception
    at.get_by_key("vista").set_value("Datos").run()
    at.button(key="demo").click().run()
    at.get_by_key("vista").set_value("Estadística").run()
    assert not at.exception
    at.button(key="stats_prepare").click().run(timeout=60)
    assert not at.exception
    raw = at.session_state["comparison_raw"]
    assert raw["semantic_source"] == "HYPOTHETICAL"
    assert len(raw["C1"]) == 300
    assert at.session_state["comparison"]["status"] == "TECHNICAL_FIXTURE_ONLY"
