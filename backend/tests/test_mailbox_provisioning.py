import secrets

import pytest
from sqlalchemy import select

from app.api.dependencies import get_automation_settings
from app.api.mailboxes import get_n8n_mailbox_client
from app.core.config import AutomationSettings
from app.core.tokens import create_access_token
from app.models import Mailbox, MailboxConnection, Role, User
from app.services.n8n_mailboxes import N8nUnavailable

pytestmark = pytest.mark.integration


class FakeN8n:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def workflow(self, mailbox_id, imap_id, automation_id):
        return {"name": f"receiver-{mailbox_id}", "nodes": [], "connections": {}, "settings": {}}

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.fail and self.fail in path:
            raise N8nUnavailable("private-password")
        if path == "/credentials":
            return {"id": body["id"]}
        if path.endswith("/test"):
            return {"status": "OK"}
        if path == "/workflows":
            return {"id": "workflow-1"}
        return {}


@pytest.fixture
def setup_connection(api_app, db_session, account, auth_settings, monkeypatch):
    mailbox = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
    mailbox.status = "PENDING"
    db_session.commit()
    client = FakeN8n()
    api_app.dependency_overrides[get_n8n_mailbox_client] = lambda: client
    api_app.dependency_overrides[get_automation_settings] = lambda: AutomationSettings(
        _env_file=None, automation_api_key=secrets.token_urlsafe(48)
    )
    monkeypatch.setattr("app.services.mailbox_provisioning.verify_gmail_access", lambda *_: None)
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    return mailbox, client, headers


def test_connect_disconnect_and_reconnect_are_owner_scoped(
    api_client, setup_connection, db_session
):
    mailbox, client, headers = setup_connection
    path = f"/api/mailboxes/{mailbox.id}"
    response = api_client.post(
        path + "/connect", json={"app_password": "private-password"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"
    assert "private-password" not in response.text
    state = db_session.scalar(
        select(MailboxConnection).where(MailboxConnection.mailbox_id == mailbox.id)
    )
    assert state.stage == "active" and not state.needs_reconciliation
    original_id = state.id
    assert client.calls[0][2]["data"]["password"] == "private-password"
    assert "private-password" not in str(client.calls[3][2])
    assert client.calls[-1][1] == "/workflows/workflow-1/publish"
    assert (
        api_client.patch(path, json={"status": "DISCONNECTED"}, headers=headers).status_code == 409
    )
    response = api_client.post(path + "/disconnect", headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "DISCONNECTED"
    assert (
        db_session.scalar(
            select(MailboxConnection).where(MailboxConnection.mailbox_id == mailbox.id)
        )
        is None
    )
    response = api_client.post(
        path + "/connect", json={"app_password": "private-password"}, headers=headers
    )
    assert response.status_code == 200
    replacement = db_session.scalar(
        select(MailboxConnection).where(MailboxConnection.mailbox_id == mailbox.id)
    )
    assert replacement.id != original_id


def test_foreign_user_cannot_connect_or_disconnect(
    api_client, setup_connection, db_session, auth_settings
):
    mailbox, client, _ = setup_connection
    other = User(
        name="Other", email="other-prov@example.com", password_hash="hash", role=Role.EMPLOYEE
    )
    db_session.add(other)
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(other.id, auth_settings)}"}
    path = f"/api/mailboxes/{mailbox.id}"
    assert (
        api_client.post(
            path + "/connect", json={"app_password": "private-password"}, headers=headers
        ).status_code
        == 404
    )
    assert api_client.post(path + "/disconnect", headers=headers).status_code == 404
    assert client.calls == []


def test_remote_error_quarantines_resources_and_prevents_automatic_retry(
    api_client, setup_connection, db_session
):
    mailbox, client, headers = setup_connection
    client.fail = "/test"
    path = f"/api/mailboxes/{mailbox.id}/connect"
    response = api_client.post(path, json={"app_password": "private-password"}, headers=headers)
    assert response.status_code == 503
    assert "private-password" not in response.text
    db_session.expire_all()
    state = db_session.scalar(
        select(MailboxConnection).where(MailboxConnection.mailbox_id == mailbox.id)
    )
    assert state.stage == "imap-created" and state.needs_reconciliation
    assert db_session.get(Mailbox, mailbox.id).status == "PENDING"
    before = len(client.calls)
    assert (
        api_client.post(
            path, json={"app_password": "private-password"}, headers=headers
        ).status_code
        == 409
    )
    assert len(client.calls) == before


def test_unpublish_failure_revokes_connection_before_remote_call(
    api_client, setup_connection, db_session
):
    mailbox, client, headers = setup_connection
    path = f"/api/mailboxes/{mailbox.id}"
    assert (
        api_client.post(path + "/connect", json={"app_password": "pw"}, headers=headers).status_code
        == 200
    )
    client.fail = "/unpublish"
    assert api_client.post(path + "/disconnect", headers=headers).status_code == 503
    db_session.expire_all()
    state = db_session.scalar(
        select(MailboxConnection).where(MailboxConnection.mailbox_id == mailbox.id)
    )
    assert state.needs_reconciliation and state.stage == "active"
    assert db_session.get(Mailbox, mailbox.id).status == "DISCONNECTED"


def test_simultaneous_connect_attempts_do_not_provision_twice(
    setup_connection, migrated_engine, account, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from fastapi import HTTPException
    from sqlalchemy.orm import Session

    from app.services.mailbox_provisioning import connect_mailbox

    mailbox, client, _ = setup_connection
    entered, resume = Event(), Event()

    def wait_verify(*_):
        entered.set()
        assert resume.wait(5)

    monkeypatch.setattr("app.services.mailbox_provisioning.verify_gmail_access", wait_verify)

    def connect():
        with Session(migrated_engine, expire_on_commit=False) as session:
            actor = session.get(User, account.id)
            try:
                connect_mailbox(
                    session,
                    actor=actor,
                    mailbox_id=mailbox.id,
                    app_password="test",
                    client=client,
                    master_key="x" * 48,
                    peer=None,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(connect)
        assert entered.wait(5)
        second = pool.submit(connect)
        resume.set()
        assert sorted([first.result(timeout=15), second.result(timeout=15)]) == [200, 409]
    assert sum(path == "/workflows" for _, path, _ in client.calls) == 1


def test_connect_with_real_http_client_against_local_n8n_simulation(
    api_app, api_client, db_session, account, auth_settings, monkeypatch
):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    from threading import Thread

    from app.services.n8n_mailboxes import N8nMailboxClient

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw else None
            calls.append((self.path, body))
            if self.path.endswith("/credentials"):
                result = {"id": body["id"]}
            elif self.path.endswith("/test"):
                result = {"status": "OK"}
            elif self.path.endswith("/workflows"):
                result = {"id": "workflow-sim"}
            else:
                result = {}
            encoded = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        template = Path(__file__).resolve().parents[2] / "n8n/workflows/bec-analysis-webhook.json"
        client = N8nMailboxClient(
            f"http://127.0.0.1:{server.server_port}", "fake-key", template, "http://backend:8000"
        )
        api_app.dependency_overrides[get_n8n_mailbox_client] = lambda: client
        api_app.dependency_overrides[get_automation_settings] = lambda: AutomationSettings(
            _env_file=None, automation_api_key="m" * 40
        )
        monkeypatch.setattr(
            "app.services.mailbox_provisioning.verify_gmail_access", lambda *_: None
        )
        mailbox = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
        mailbox.status = "PENDING"
        db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
        response = api_client.post(
            f"/api/mailboxes/{mailbox.id}/connect",
            json={"app_password": "fake-pass"},
            headers=headers,
        )
        assert response.status_code == 200
        assert calls[0][1]["data"]["password"] == "fake-pass"
        workflow = calls[3][1]
        assert "fake-pass" not in json.dumps(workflow)
        assert "bg2." not in json.dumps(workflow)
        assert calls[-1][0] == "/api/v1/workflows/workflow-sim/publish"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_already_connected_address_is_rejected_before_creating_resources(
    api_client, setup_connection, db_session
):
    mailbox, client, headers = setup_connection
    other = User(
        name="Owner", email="owner-prov@example.com", password_hash="hash", role=Role.EMPLOYEE
    )
    db_session.add(other)
    db_session.flush()
    db_session.add(
        Mailbox(
            user_id=other.id, email_address=mailbox.email_address, provider="gmail", status="ACTIVE"
        )
    )
    db_session.commit()
    response = api_client.post(
        f"/api/mailboxes/{mailbox.id}/connect", json={"app_password": "pw"}, headers=headers
    )
    assert response.status_code == 409
    assert client.calls == []


def test_publish_failure_keeps_workflow_quarantined(api_client, setup_connection, db_session):
    mailbox, client, headers = setup_connection
    client.fail = "/publish"
    response = api_client.post(
        f"/api/mailboxes/{mailbox.id}/connect", json={"app_password": "pw"}, headers=headers
    )
    assert response.status_code == 503
    db_session.expire_all()
    state = db_session.scalar(
        select(MailboxConnection).where(MailboxConnection.mailbox_id == mailbox.id)
    )
    assert state.workflow_id == "workflow-1"
    assert state.stage == "workflow-created"
    assert state.needs_reconciliation
    assert db_session.get(Mailbox, mailbox.id).status == "PENDING"
