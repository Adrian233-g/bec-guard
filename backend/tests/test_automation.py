import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.api.dependencies import get_automation_settings
from app.api.email_analysis import get_analyzer_factory
from app.core.config import AutomationSettings
from app.core.tokens import create_access_token
from app.models import AuditLog, BECAlert, Email, EmailAnalysis, ExecutiveContact, Mailbox
from app.services.semantic_analysis import LLMErrorCode

pytestmark = pytest.mark.integration


@pytest.fixture
def automation_setup(api_app, analysis_stub, db_session, email_payload, account):
    key = secrets.token_urlsafe(48)
    mailbox_id = db_session.scalar(select(Mailbox.id).where(Mailbox.user_id == account.id))
    settings = AutomationSettings(
        _env_file=None, automation_api_key=key, automation_mailbox_id=str(mailbox_id)
    )
    api_app.dependency_overrides[get_automation_settings] = lambda: settings
    api_app.dependency_overrides[get_analyzer_factory] = lambda: lambda: analysis_stub
    db_session.add(ExecutiveContact(name="Ana Pérez", position="CEO", email="ana@empresa.example"))
    db_session.commit()
    payload = {
        **email_payload,
        "sender_name": "Ana Pérez",
        "sender_email": "ana@ernpresa.example",
        "subject": "Pago urgente",
        "body_text": "Soy la directora, paga hoy. No consultes a finanzas.",
        "authentication_results": "mx; dmarc=fail",
    }
    return {"X-BEC-Automation-Key": key}, payload


@pytest.mark.parametrize(
    "kind,expected", [("valid", 201), ("invalid", 401), ("missing", 401), ("unicode", 401)]
)
def test_automation_key(api_client, automation_setup, kind, expected, caplog):
    headers, payload = automation_setup
    supplied = (
        headers
        if kind == "valid"
        else ({"X-BEC-Automation-Key": "incorrect-key"} if kind == "invalid" else {})
    )
    if kind == "unicode":
        supplied = {b"X-BEC-Automation-Key": "á".encode()}
    response = api_client.post("/api/automation/emails", json=payload, headers=supplied)
    assert response.status_code == expected
    assert headers["X-BEC-Automation-Key"] not in response.text + caplog.text


@pytest.mark.parametrize("key", ["", "short"])
def test_unconfigured_automation_is_lazy_503(api_app, api_client, email_payload, key, caplog):
    api_app.dependency_overrides[get_automation_settings] = lambda: AutomationSettings(
        _env_file=None, automation_api_key=key
    )
    assert api_client.get("/openapi.json").status_code == 200
    response = api_client.post("/api/automation/emails", json=email_payload)
    assert response.status_code == 503
    assert response.json() == {"detail": "Automation unavailable"}
    assert (
        repr(AutomationSettings(_env_file=None, automation_api_key="hidden-value")).find(
            "hidden-value"
        )
        < 0
    )


def test_ingest_idempotent_and_human_still_409(
    api_client,
    automation_setup,
    db_session,
    account,
    auth_settings,
):
    headers, payload = automation_setup
    first = api_client.post("/api/automation/emails", json=payload, headers=headers)
    assert first.status_code == 201 and first.json()["created"] is True
    second = api_client.post(
        "/api/automation/emails",
        headers=headers,
        json={**payload, "subject": "Must not replace", "body_text": "Different"},
    )
    assert second.status_code == 200 and second.json()["created"] is False
    assert second.json()["email"] == first.json()["email"]
    [audit] = list(db_session.scalars(select(AuditLog)))
    assert audit.action == "EMAIL_INGESTED"
    assert audit.actor_user_id is audit.actor_role is audit.details is None
    jwt_headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    assert api_client.post("/api/emails", json=payload, headers=jwt_headers).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Email)) == 1
    variant = {**payload, "message_id": payload["message_id"].lower()}
    assert (
        api_client.post("/api/automation/emails", json=variant, headers=headers).status_code == 201
    )


def test_scopes_do_not_cross(api_client, automation_setup, account, auth_settings):
    headers, payload = automation_setup
    for path in ["/api/auth/me", "/api/alerts", "/api/emails", "/api/vendors", "/api/executives"]:
        assert api_client.get(path, headers=headers).status_code == 401
    assert api_client.post("/api/emails", json=payload, headers=headers).status_code == 401
    assert api_client.post(f"/api/emails/{uuid4()}/analyze", headers=headers).status_code == 401
    jwt_headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=jwt_headers).status_code
        == 401
    )
    assert (
        api_client.post(
            f"/api/automation/emails/{uuid4()}/analyze", headers=jwt_headers
        ).status_code
        == 401
    )


def test_automation_high_alert_idempotence_and_audit(
    api_client, automation_setup, db_session, analysis_stub
):
    headers, payload = automation_setup
    email = api_client.post("/api/automation/emails", json=payload, headers=headers).json()["email"]
    path = f"/api/automation/emails/{email['id']}/analyze"
    first = api_client.post(path, headers=headers)
    assert first.status_code == 200
    result = first.json()
    assert result["analysis"]["status"] == "COMPLETED"
    assert result["analysis"]["risk_level"] == "CRITICAL" and result["alert_id"] is not None
    assert api_client.post(path, headers=headers).json() == result
    assert analysis_stub.calls == 1
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1
    events = list(db_session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)))
    assert {e.action for e in events} == {"EMAIL_INGESTED", "EMAIL_ANALYZED", "BEC_ALERT_CREATED"}
    assert len(events) == 3
    assert all(e.actor_user_id is e.actor_role is e.details is None for e in events)


@pytest.mark.parametrize("semantic_score,level", [(0, "LOW"), (100, "MEDIUM")])
def test_automation_low_medium_have_no_alert(
    api_client, automation_setup, db_session, analysis_stub, semantic_score, level
):
    headers, payload = automation_setup
    analysis_stub.score = semantic_score
    body = {
        **payload,
        "sender_name": "Unknown Person",
        "sender_email": "person@other.example",
        "subject": "Reunión",
        "body_text": "Reunión mañana",
        "reply_to": None,
        "return_path": None,
        "authentication_results": None,
    }
    email_id = api_client.post("/api/automation/emails", json=body, headers=headers).json()[
        "email"
    ]["id"]
    response = api_client.post(f"/api/automation/emails/{email_id}/analyze", headers=headers)
    assert response.status_code == 200
    assert response.json()["analysis"]["risk_level"] == level
    assert response.json()["alert_id"] is None
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0


@pytest.mark.parametrize(
    "code,http",
    [
        (LLMErrorCode.NOT_CONFIGURED, 503),
        (LLMErrorCode.TIMEOUT, 502),
        (LLMErrorCode.RATE_LIMITED, 429),
        (LLMErrorCode.PROVIDER_ERROR, 502),
        (LLMErrorCode.INVALID_OUTPUT, 502),
    ],
)
def test_error_and_retry_same_analysis_one_alert(
    api_client, automation_setup, db_session, analysis_stub, code, http
):
    headers, payload = automation_setup
    email_id = api_client.post("/api/automation/emails", json=payload, headers=headers).json()[
        "email"
    ]["id"]
    path = f"/api/automation/emails/{email_id}/analyze"
    analysis_stub.failure = code
    failed = api_client.post(path, headers=headers)
    assert failed.status_code == http
    failure = failed.json()
    assert failure["alert_id"] is None and failure["analysis"]["status"] == "ERROR"
    assert failure["analysis"]["risk_level"] is failure["analysis"]["risk_score"] is None
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
    analysis_stub.failure = None
    retry = api_client.post(path, headers=headers)
    assert retry.status_code == 200
    assert retry.json()["analysis"]["id"] == failure["analysis"]["id"]
    assert retry.json()["alert_id"] is not None
    assert api_client.post(path, headers=headers).json() == retry.json()
    assert analysis_stub.calls == 2
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1


def test_missing_and_invalid_requests(api_client, automation_setup):
    headers, payload = automation_setup
    assert (
        api_client.post(f"/api/automation/emails/{uuid4()}/analyze", headers=headers).status_code
        == 404
    )
    assert api_client.post("/api/automation/emails/bad/analyze", headers=headers).status_code == 400
    assert (
        api_client.post(
            "/api/automation/emails", headers=headers, json={**payload, "label": "BEC"}
        ).status_code
        == 400
    )


def test_concurrent_ingestion_uses_unique_winner(
    api_client, automation_setup, db_session, monkeypatch
):
    from app.services import email_ingestion

    headers, payload = automation_setup
    barrier = Barrier(2)
    original = email_ingestion.ingest_email

    def synchronized(*args, **kwargs):
        barrier.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(email_ingestion, "ingest_email", synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(api_client.post, "/api/automation/emails", json=payload, headers=headers)
            for _ in range(2)
        ]
        responses = [f.result(timeout=15) for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json()["email"]["id"] == responses[1].json()["email"]["id"]
    assert db_session.scalar(select(func.count()).select_from(Email)) == 1
    assert list(db_session.scalars(select(AuditLog.action))) == ["EMAIL_INGESTED"]


def test_concurrent_pipeline_one_call_analysis_alert(
    api_client, automation_setup, analysis_stub, db_session
):
    headers, payload = automation_setup
    email_id = api_client.post("/api/automation/emails", json=payload, headers=headers).json()[
        "email"
    ]["id"]
    path = f"/api/automation/emails/{email_id}/analyze"
    analysis_stub.entered, analysis_stub.release = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api_client.post, path, headers=headers)
        try:
            assert analysis_stub.entered.wait(10)
            second = pool.submit(api_client.post, path, headers=headers)
        finally:
            analysis_stub.release.set()
        results = [first.result(timeout=15), second.result(timeout=15)]
    assert all(r.status_code == 200 for r in results)
    assert results[0].json() == results[1].json()
    assert analysis_stub.calls == 1
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1


def test_constant_time_key_comparison(api_client, automation_setup, monkeypatch):
    from app.api import dependencies

    original = dependencies.secrets.compare_digest
    calls = []

    def compare(left, right):
        calls.append((type(left), type(right)))
        return original(left, right)

    monkeypatch.setattr(dependencies.secrets, "compare_digest", compare)
    headers, payload = automation_setup
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=headers).status_code == 201
    )
    assert calls == [(bytes, bytes)]


def test_automation_alert_audit_failure_is_atomic(
    api_client,
    automation_setup,
    db_session,
    migrated_engine,
):
    headers, payload = automation_setup
    email_id = api_client.post("/api/automation/emails", json=payload, headers=headers).json()[
        "email"
    ]["id"]
    with migrated_engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION public.reject_test_automation_alert() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.action = 'BEC_ALERT_CREATED' AND NEW.actor_user_id IS NULL THEN
                    RAISE EXCEPTION 'Test audit failure' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END; $$
        """)
        )
        connection.execute(
            text("""
            CREATE TRIGGER reject_test_automation_alert BEFORE INSERT ON public.audit_log
            FOR EACH ROW EXECUTE FUNCTION public.reject_test_automation_alert()
        """)
        )
    try:
        response = api_client.post(f"/api/automation/emails/{email_id}/analyze", headers=headers)
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 0
        assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
        assert list(db_session.scalars(select(AuditLog.action))) == ["EMAIL_INGESTED"]
    finally:
        db_session.rollback()
        with migrated_engine.begin() as connection:
            connection.execute(
                text("DROP TRIGGER reject_test_automation_alert ON public.audit_log")
            )
            connection.execute(text("DROP FUNCTION public.reject_test_automation_alert()"))


def test_connector_ignores_recipient_headers_and_rejects_mailbox_override(
    api_client, automation_setup, db_session, account, auth_settings
):
    from app.models import Role, User

    headers, payload = automation_setup
    attacker = User(
        name="Other", email="other@example.com", password_hash="test", role=Role.EMPLOYEE
    )
    db_session.add(attacker)
    db_session.commit()
    token = {"Authorization": f"Bearer {create_access_token(attacker.id, auth_settings)}"}
    registered = api_client.post(
        "/api/mailboxes",
        json={"email_address": "claimed@example.com", "provider": "gmail"},
        headers=token,
    )
    assert registered.status_code == 201
    assert registered.json()["status"] == "PENDING"
    claimed_id = registered.json()["id"]
    assert (
        api_client.patch(
            f"/api/mailboxes/{claimed_id}", json={"status": "ACTIVE"}, headers=token
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            "/api/automation/emails", json={**payload, "mailbox_id": claimed_id}, headers=headers
        ).status_code
        == 400
    )
    assert (
        api_client.post(
            f"/api/automation/emails?mailbox_id={claimed_id}", json=payload, headers=headers
        ).status_code
        == 400
    )
    response = api_client.post(
        "/api/automation/emails",
        json={**payload, "to_recipients": ["claimed@example.com"]},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["email"]["mailbox_id"] != claimed_id
    assert (
        api_client.get(f"/api/emails/{response.json()['email']['id']}", headers=token).status_code
        == 404
    )
    own_token = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    assert (
        api_client.get(
            f"/api/emails/{response.json()['email']['id']}", headers=own_token
        ).status_code
        == 200
    )


def test_connector_fails_closed_if_bound_mailbox_disconnected(
    api_client, automation_setup, db_session, account
):
    from app.models import Role, User

    headers, payload = automation_setup
    bound = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
    bound.status = "DISCONNECTED"
    other = User(name="Other", email="other2@example.com", password_hash="test", role=Role.EMPLOYEE)
    db_session.add(other)
    db_session.flush()
    db_session.add(
        Mailbox(
            user_id=other.id, email_address="other2@example.com", provider="gmail", status="ACTIVE"
        )
    )
    db_session.commit()
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=headers).status_code == 503
    )
    assert db_session.scalar(select(func.count()).select_from(Email)) == 0


def test_connector_cannot_analyze_another_mailbox(
    api_client, automation_setup, db_session, analysis_stub
):
    from datetime import UTC, datetime

    from app.models import Role, User

    headers, _ = automation_setup
    other = User(name="Other", email="other3@example.com", password_hash="test", role=Role.EMPLOYEE)
    db_session.add(other)
    db_session.flush()
    mailbox = Mailbox(
        user_id=other.id, email_address="other3@example.com", provider="gmail", status="ACTIVE"
    )
    db_session.add(mailbox)
    db_session.flush()
    email = Email(
        mailbox_id=mailbox.id,
        message_id="<other@example.com>",
        sender_email="s@example.com",
        to_recipients=[],
        cc_recipients=[],
        subject="Private",
        body_text="Private",
        received_at=datetime.now(UTC),
    )
    db_session.add(email)
    db_session.commit()
    assert (
        api_client.post(f"/api/automation/emails/{email.id}/analyze", headers=headers).status_code
        == 404
    )
    assert analysis_stub.calls == 0


def test_connector_requires_server_mailbox_configuration(api_app, api_client, email_payload):
    key = secrets.token_urlsafe(48)
    api_app.dependency_overrides[get_automation_settings] = lambda: AutomationSettings(
        _env_file=None, automation_api_key=key, automation_mailbox_id=""
    )
    response = api_client.post(
        "/api/automation/emails", json=email_payload, headers={"X-BEC-Automation-Key": key}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Automation mailbox not configured"


def test_each_connector_is_scoped_to_its_own_mailbox(
    api_client, automation_setup, db_session, account, analysis_stub
):
    from app.core.connector_tokens import connector_token
    from app.models import MailboxConnection, Role, User

    headers, payload = automation_setup
    master = headers["X-BEC-Automation-Key"]
    owner_mailbox = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
    other = User(
        name="Other", email="other-connector@example.com", password_hash="test", role=Role.EMPLOYEE
    )
    db_session.add(other)
    db_session.flush()
    other_mailbox = Mailbox(
        user_id=other.id,
        email_address="other-connector@gmail.com",
        provider="gmail",
        status="ACTIVE",
    )
    db_session.add(other_mailbox)
    db_session.flush()
    owner_connection = MailboxConnection(
        mailbox_id=owner_mailbox.id,
        stage="active",
        imap_credential_id="ownerimap",
        automation_credential_id="ownerauth",
        workflow_id="ownerwf",
    )
    other_connection = MailboxConnection(
        mailbox_id=other_mailbox.id,
        stage="active",
        imap_credential_id="otherimap",
        automation_credential_id="otherauth",
        workflow_id="otherwf",
    )
    db_session.add_all([owner_connection, other_connection])
    db_session.commit()
    owner_key = {
        "X-BEC-Automation-Key": connector_token(master, owner_mailbox.id, owner_connection.id)
    }
    other_key = {
        "X-BEC-Automation-Key": connector_token(master, other_mailbox.id, other_connection.id)
    }
    first = api_client.post("/api/automation/emails", json=payload, headers=owner_key)
    second = api_client.post("/api/automation/emails", json=payload, headers=other_key)
    assert first.status_code == second.status_code == 201
    assert first.json()["email"]["mailbox_id"] == str(owner_mailbox.id)
    assert second.json()["email"]["mailbox_id"] == str(other_mailbox.id)
    assert (
        api_client.post(
            f"/api/automation/emails/{first.json()['email']['id']}/analyze", headers=other_key
        ).status_code
        == 404
    )
    assert analysis_stub.calls == 0
    forged = {
        "X-BEC-Automation-Key": connector_token(
            master, owner_mailbox.id, owner_connection.id
        ).replace(owner_mailbox.id.hex, other_mailbox.id.hex)
    }
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=forged).status_code == 401
    )
    other_mailbox.status = "DISCONNECTED"
    db_session.commit()
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=other_key).status_code
        == 503
    )


def test_connector_key_is_revoked_by_connection_state(
    api_client, automation_setup, db_session, account
):
    from app.core.connector_tokens import connector_token
    from app.models import MailboxConnection

    headers, payload = automation_setup
    mailbox = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
    connection = MailboxConnection(
        mailbox_id=mailbox.id,
        stage="active",
        imap_credential_id="imap",
        automation_credential_id="auth",
        workflow_id="workflow",
    )
    db_session.add(connection)
    db_session.commit()
    token = connector_token(headers["X-BEC-Automation-Key"], mailbox.id, connection.id)
    scoped_headers = {"X-BEC-Automation-Key": token}
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=scoped_headers).status_code
        == 201
    )
    connection.stage = "workflow-unpublished"
    db_session.commit()
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=scoped_headers).status_code
        == 503
    )
    db_session.delete(connection)
    db_session.flush()
    replacement = MailboxConnection(
        mailbox_id=mailbox.id,
        stage="active",
        imap_credential_id="imap2",
        automation_credential_id="auth2",
        workflow_id="workflow2",
    )
    db_session.add(replacement)
    db_session.commit()
    assert (
        api_client.post("/api/automation/emails", json=payload, headers=scoped_headers).status_code
        == 503
    )
    new_token = connector_token(headers["X-BEC-Automation-Key"], mailbox.id, replacement.id)
    assert new_token != token
    assert (
        api_client.post(
            "/api/automation/emails", json=payload, headers={"X-BEC-Automation-Key": new_token}
        ).status_code
        == 200
    )
    replacement.needs_reconciliation = True
    db_session.commit()
    assert (
        api_client.post(
            "/api/automation/emails", json=payload, headers={"X-BEC-Automation-Key": new_token}
        ).status_code
        == 503
    )
