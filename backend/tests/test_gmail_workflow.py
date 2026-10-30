import json
import subprocess
from pathlib import Path

import pytest

from app.schemas.email import EmailIngestRequest

WORKFLOW = Path(__file__).resolve().parents[2] / "n8n/workflows/bec-analysis-webhook.json"


def normalize(mail):
    workflow = json.loads(WORKFLOW.read_text())
    code = next(n for n in workflow["nodes"] if n["name"] == "Normalize IMAP")["parameters"][
        "jsCode"
    ]
    runner = (
        "const $json = JSON.parse(process.argv[1]);\n"
        + "const run = () => {\n"
        + code
        + "\n};\nprocess.stdout.write(JSON.stringify(run().json));"
    )
    result = subprocess.run(
        ["node", "-e", runner, json.dumps(mail)], capture_output=True, text=True
    )
    if result.returncode:
        raise ValueError(result.stderr)
    return json.loads(result.stdout)["email"]


def test_gmail_normalization_preserves_email_and_contract():
    mail = {
        "id": "gmail-123",
        "messageId": "<one@example.com>",
        "from": {"value": [{"name": "Nora Prisma", "address": "nora@example.com"}]},
        "to": {"value": [{"address": "finance@example.com"}]},
        "cc": {"value": [{"address": "team@example.com"}]},
        "replyTo": {"value": [{"address": "reply@example.com"}]},
        "headers": {
            "return-path": "Return-Path: <bounce@example.com>",
            "authentication-results": "Authentication-Results: mx.test; dkim=pass",
        },
        "subject": "Transferencia",
        "text": "Por favor verifica el pago.",
        "date": "2026-10-30T12:00:00.000Z",
    }
    result = normalize(mail)
    EmailIngestRequest.model_validate(result)
    assert result["message_id"] == "<one@example.com>"
    assert result["thread_id"] is None
    assert result["sender_email"] == "nora@example.com"
    assert result["reply_to"] == "reply@example.com"
    assert result["return_path"] == "bounce@example.com"
    assert result["authentication_results"] == "mx.test; dkim=pass"
    assert result["body_text"] == mail["text"]
    assert result["to_recipients"] == ["finance@example.com"]


def test_missing_id_and_ambiguous_input_are_rejected():
    mail = {"from": {"value": [{"address": "a@example.com"}]}}
    with pytest.raises(ValueError, match="IMAP_MISSING_MESSAGE_ID"):
        normalize(mail)
    with pytest.raises(ValueError, match="IMAP_INVALID_FROM"):
        normalize({"messageId": "<id@example.com>"})
    with pytest.raises(ValueError, match="IMAP_MISSING_TEXT"):
        normalize({**mail, "messageId": "<id@example.com>", "html": "<p>Hello</p>"})


def test_gmail_workflow_is_inactive_and_calls_automation_api():
    workflow = json.loads(WORKFLOW.read_text())
    nodes = {node["name"]: node for node in workflow["nodes"]}
    assert not workflow["active"] and workflow["pinData"] == {}
    assert nodes["Email Trigger (IMAP)"]["disabled"] is True
    assert nodes["Email Trigger (IMAP)"]["parameters"]["format"] == "resolved"
    assert nodes["Email Trigger (IMAP)"]["parameters"]["postProcessAction"] == "nothing"
    assert nodes["Ingest email"]["retryOnFail"] is False
    assert nodes["Analyze email"]["retryOnFail"] is False
    assert "/api/automation/emails" in nodes["Ingest email"]["parameters"]["url"]
    assert "/analyze" in nodes["Analyze email"]["parameters"]["url"]
    assert "$env" not in WORKFLOW.read_text()
