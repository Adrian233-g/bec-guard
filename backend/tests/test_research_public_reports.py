"""Public summaries expose only consistent aggregated metrics in the laboratory."""

import json
from pathlib import Path

import pytest

from research.bec_training.public_reports import AUX, V1, V2, summarize_public_report


def _report(status=V1):
    rows = {
        "bec2": {"evaluated": 2, "tp": 1, "fn": 1, "recall": 0.5},
        "enron": {"evaluated": 4, "fp": 1, "tn": 3, "fpr": 0.25},
        "ceas08": {"evaluated": 2, "fp": 1, "tn": 1, "fpr": 0.5},
    }
    if status == V2:
        return {
            "status": V2,
            "model_sha256": "a" * 64,
            "diagnostic_gate": "FAILS_PROXY_TARGETS",
            "external_test": {"bec2": rows["bec2"], "ceas08_ham": rows["ceas08"]},
        }
    return {"status": V1, "model_sha256": "a" * 64, "cohorts": rows}


@pytest.mark.parametrize("status", [V1, V2])
def test_public_report_checks_denominators_and_discards_untrusted_fields(status):
    report = _report(status)
    report["email_body"] = "Never show this message"
    view = summarize_public_report(json.dumps(report).encode())
    assert len(view["rows"]) == (3 if status == V1 else 2)
    assert "Never show this message" not in str(view)
    rows = report["cohorts"] if status == V1 else report["external_test"]
    rows["bec2"]["recall"] = 1.0
    with pytest.raises(ValueError, match="Tasa"):
        summarize_public_report(json.dumps(report).encode())


def test_public_transfer_view_renders_aggregates_without_emails():
    streamlit = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    assert streamlit is not None
    entry = Path(__file__).resolve().parents[1] / "research" / "streamlit_app.py"
    at = AppTest.from_file(str(entry), default_timeout=30).run()
    at.get_by_key("vista").set_value("Transferencia").run()
    assert not at.exception
    at.file_uploader(key="public_report").upload(
        "benchmark.json", json.dumps(_report()).encode()
    ).run()
    assert not at.exception
    assert len(at.dataframe) == 1
    assert "Never show" not in str(at)


def test_auxiliary_phishing_report_shows_rates_without_claiming_bec_recall():
    row = {
        "model_sha256": "b" * 64,
        "bec_recall": "NOT_ESTIMABLE_NO_BEC_SUBTYPE_LABEL",
        "benign_count": 2,
        "generic_phishing_count": 3,
        "benign_false_alarms": 2,
        "benign_fpr_synthetic": 1.0,
        "generic_phishing_flagged": 3,
        "generic_phishing_flag_rate": 1.0,
    }
    report = {
        "status": AUX,
        "corpus": {"unique_labels": {"0": 2, "1": 3}},
        "assist_eligible": False,
        "models": {"v1": row, "v2": {**row, "benign_false_alarms": 0, "benign_fpr_synthetic": 0.0}},
        "body": "Never show this message",
    }
    view = summarize_public_report(json.dumps(report).encode())
    assert len(view["rows"]) == 4
    assert view["rows"][1]["métrica"] == "Marcación (no recall BEC)"
    assert "Never show this message" not in str(view)
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    entry = Path(__file__).resolve().parents[1] / "research" / "streamlit_app.py"
    at = AppTest.from_file(str(entry), default_timeout=30).run()
    at.get_by_key("vista").set_value("Transferencia").run()
    at.file_uploader(key="public_report").upload("aux.json", json.dumps(report).encode()).run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 4
    report["models"]["v2"]["benign_count"] = 3
    with pytest.raises(ValueError, match="cohortes diferentes"):
        summarize_public_report(json.dumps(report).encode())
