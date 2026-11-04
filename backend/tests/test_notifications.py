from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core.tokens import create_access_token
from app.models import EmailAnalysis, Mailbox, Notification, Role, User
from app.schemas.email import EmailIngestRequest
from app.services.alerts import ensure_alert_for_analysis
from app.services.email_ingestion import ingest_email
from app.services.hybrid_scoring import risk_level

pytestmark = pytest.mark.integration


def create_user(db_session, *, name, email, role, is_active=True, with_mailbox=True):
    user = User(name=name, email=email, password_hash="opaque", role=role, is_active=is_active)
    db_session.add(user)
    db_session.flush()
    if with_mailbox:
        db_session.add(Mailbox(user_id=user.id, email_address=email, status="ACTIVE"))
    db_session.commit()
    return user


def create_analysis(db_session, owner, email_payload, *, score=85, message_id="<notice@example>"):
    mailbox_id = db_session.scalar(select(Mailbox.id).where(Mailbox.user_id == owner.id))
    email = ingest_email(
        db_session,
        EmailIngestRequest(**{**email_payload, "message_id": message_id}),
        mailbox_id=mailbox_id,
        actor=owner,
    )
    analysis = EmailAnalysis(
        email_id=email.id,
        status="COMPLETED",
        deterministic_score=100,
        semantic_score=score,
        risk_score=score,
        risk_level=risk_level(score),
        bec_type="OTHER",
        signals=[],
        summary="Resultado controlado de pruebas.",
        recommended_action="Verificar identidad.",
        provider="openai",
        model="unit-test-model",
        policy_version="det-v1/semantic-v1/hybrid-v1",
        analyzed_at=datetime.now(UTC),
    )
    db_session.add(analysis)
    db_session.commit()
    return email, analysis


@pytest.fixture
def notification_setup(db_session, email_payload):
    owner = create_user(db_session, name="Owner", email="owner@example.com", role=Role.EMPLOYEE)
    admin = create_user(db_session, name="Admin", email="admin@example.com", role=Role.ADMIN)
    analyst = create_user(
        db_session, name="Analyst", email="analyst@example.com", role=Role.ANALYST
    )
    other_employee = create_user(
        db_session, name="Other Employee", email="other@example.com", role=Role.EMPLOYEE
    )
    inactive_analyst = create_user(
        db_session,
        name="Inactive Analyst",
        email="inactive@example.com",
        role=Role.ANALYST,
        is_active=False,
    )
    email, analysis = create_analysis(db_session, owner, email_payload)
    alert = ensure_alert_for_analysis(db_session, analysis, actor=None)
    db_session.commit()
    return {
        "owner": owner,
        "admin": admin,
        "analyst": analyst,
        "other_employee": other_employee,
        "inactive_analyst": inactive_analyst,
        "email": email,
        "analysis": analysis,
        "alert": alert,
    }


def headers_for(user, auth_settings):
    return {"Authorization": f"Bearer {create_access_token(user.id, auth_settings)}"}


def test_alert_notifies_owner_and_active_security_team_once(db_session, notification_setup):
    setup = notification_setup
    rows = list(db_session.scalars(select(Notification)))
    expected = {setup["owner"].id, setup["admin"].id, setup["analyst"].id}
    assert {row.user_id for row in rows} == expected
    assert all(
        row.alert_id == setup["alert"].id and row.kind == "BEC_ALERT" and row.read_at is None
        for row in rows
    )

    again = ensure_alert_for_analysis(db_session, setup["analysis"], actor=None)
    db_session.commit()
    assert again.id == setup["alert"].id
    assert db_session.scalar(select(func.count()).select_from(Notification)) == 3


def test_below_threshold_does_not_notify(db_session, email_payload):
    owner = create_user(db_session, name="Owner", email="owner@example.com", role=Role.EMPLOYEE)
    _, analysis = create_analysis(db_session, owner, email_payload, score=49)
    assert ensure_alert_for_analysis(db_session, analysis, actor=None) is None
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Notification)) == 0


def test_users_only_read_their_own_notifications(api_client, auth_settings, notification_setup):
    setup = notification_setup
    owner = headers_for(setup["owner"], auth_settings)
    admin = headers_for(setup["admin"], auth_settings)
    other = headers_for(setup["other_employee"], auth_settings)

    owner_rows = api_client.get("/api/notifications", headers=owner).json()
    assert len(owner_rows) == 1
    [notice] = owner_rows
    assert notice["alert_id"] == str(setup["alert"].id)
    assert notice["subject"] == setup["email"].subject
    assert notice["sender_email"] == setup["email"].sender_email
    assert notice["risk_level"] == "CRITICAL" and notice["risk_score"] == 85
    assert notice["alert_status"] == "OPEN" and notice["read_at"] is None
    assert "body_text" not in notice

    assert len(api_client.get("/api/notifications", headers=admin).json()) == 1
    assert api_client.get("/api/notifications", headers=other).json() == []
    assert api_client.get("/api/notifications/unread-count", headers=other).json() == {"count": 0}
    assert api_client.get("/api/notifications/unread-count", headers=owner).json() == {"count": 1}

    # The recipient can open the linked alert; another employee cannot.
    assert api_client.get(f"/api/alerts/{setup['alert'].id}", headers=owner).status_code == 200
    assert api_client.get(f"/api/alerts/{setup['alert'].id}", headers=other).status_code == 404

    assert api_client.get("/api/notifications").status_code == 401
    assert api_client.get("/api/notifications?limit=0", headers=owner).status_code == 400
    assert api_client.get("/api/notifications?offset=-1", headers=owner).status_code == 400


def test_mark_read_and_read_all(api_client, auth_settings, notification_setup):
    setup = notification_setup
    owner = headers_for(setup["owner"], auth_settings)
    analyst = headers_for(setup["analyst"], auth_settings)
    [notice] = api_client.get("/api/notifications", headers=owner).json()

    # Another recipient cannot mark someone else's notice.
    assert (
        api_client.post(f"/api/notifications/{notice['id']}/read", headers=analyst).status_code
        == 404
    )
    post = api_client.post(f"/api/notifications/{notice['id']}/read", headers=owner)
    assert post.status_code == 204
    assert api_client.get("/api/notifications/unread-count", headers=owner).json() == {"count": 0}
    assert api_client.get("/api/notifications?unread_only=true", headers=owner).json() == []

    remaining = api_client.get("/api/notifications", headers=owner).json()
    assert len(remaining) == 1 and remaining[0]["read_at"] is not None
    # Marking an already read notice is idempotent.
    post = api_client.post(f"/api/notifications/{notice['id']}/read", headers=owner)
    assert post.status_code == 204

    rows = api_client.get("/api/notifications", headers=analyst).json()
    assert len(rows) == 1
    assert api_client.post("/api/notifications/read-all", headers=analyst).json() == {"updated": 1}
    assert api_client.post("/api/notifications/read-all", headers=analyst).json() == {"updated": 0}
    assert api_client.get("/api/notifications/unread-count", headers=analyst).json() == {"count": 0}
    assert api_client.post("/api/notifications/read-all").status_code == 401
    assert api_client.post(f"/api/notifications/{notice['id']}/read").status_code == 401
    assert api_client.post("/api/notifications/not-a-uuid/read", headers=owner).status_code == 400


def test_demoted_analyst_cannot_read_unowned_alert_notices(
    api_client, auth_settings, notification_setup, db_session
):
    analyst = notification_setup["analyst"]
    headers = headers_for(analyst, auth_settings)
    [notice] = api_client.get("/api/notifications", headers=headers).json()
    analyst.role = Role.EMPLOYEE
    db_session.commit()
    assert api_client.get("/api/notifications", headers=headers).json() == []
    assert api_client.get("/api/notifications/unread-count", headers=headers).json() == {"count": 0}
    assert (
        api_client.post(f"/api/notifications/{notice['id']}/read", headers=headers).status_code
        == 404
    )
    assert api_client.post("/api/notifications/read-all", headers=headers).json() == {"updated": 0}
