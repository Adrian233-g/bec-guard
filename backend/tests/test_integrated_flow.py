"""End-to-end simulated flow: employee mail, alert, notice, review and audit."""

import secrets

import pytest
from sqlalchemy import func, select

from app.api.dependencies import get_automation_settings
from app.api.email_analysis import get_analyzer_factory
from app.core.config import AutomationSettings
from app.core.tokens import create_access_token
from app.models import BECAlert, ExecutiveContact, Mailbox, Notification, Role, User

pytestmark = pytest.mark.integration


def create_user(db_session, *, name, email, role, with_mailbox=False):
    user = User(name=name, email=email, password_hash="opaque", role=role)
    db_session.add(user)
    db_session.flush()
    if with_mailbox:
        db_session.add(Mailbox(user_id=user.id, email_address=email, status="ACTIVE"))
    db_session.commit()
    return user


def headers_for(user, auth_settings):
    return {"Authorization": f"Bearer {create_access_token(user.id, auth_settings)}"}


@pytest.fixture
def integrated_setup(api_app, db_session, analysis_stub, email_payload, auth_settings):
    employee = create_user(
        db_session,
        name="Empleada",
        email="employee@example.com",
        role=Role.EMPLOYEE,
        with_mailbox=True,
    )
    other_employee = create_user(
        db_session,
        name="Otro empleado",
        email="other-employee@example.com",
        role=Role.EMPLOYEE,
        with_mailbox=True,
    )
    analyst = create_user(
        db_session, name="Analista", email="analyst@example.com", role=Role.ANALYST
    )
    admin = create_user(db_session, name="Admin", email="admin@example.com", role=Role.ADMIN)
    mailbox_id = db_session.scalar(select(Mailbox.id).where(Mailbox.user_id == employee.id))
    key = secrets.token_urlsafe(48)
    api_app.dependency_overrides[get_automation_settings] = lambda: AutomationSettings(
        _env_file=None, automation_api_key=key, automation_mailbox_id=str(mailbox_id)
    )
    api_app.dependency_overrides[get_analyzer_factory] = lambda: lambda: analysis_stub
    db_session.add(ExecutiveContact(name="Ana Pérez", position="CEO", email="ana@empresa.example"))
    db_session.commit()

    strong = {
        **email_payload,
        "message_id": "<integrated-high@example.com>",
        "sender_name": "Ana Pérez",
        "sender_email": "ana@ernpresa.example",
        "reply_to": "reply@other.example",
        "subject": "Pago urgente",
        "body_text": "Soy la directora, paga hoy. No consultes a finanzas.",
        "authentication_results": "mx; dmarc=fail",
    }
    weak = {
        **email_payload,
        "message_id": "<integrated-medium@example.com>",
        "sender_name": "Unknown Person",
        "sender_email": "person@other.example",
        "reply_to": None,
        "return_path": None,
        "subject": "Reunión",
        "body_text": "Reunión mañana",
        "authentication_results": None,
    }
    return {
        "employee": employee,
        "other_employee": other_employee,
        "analyst": analyst,
        "admin": admin,
        "automation": {"X-BEC-Automation-Key": key},
        "employee_headers": headers_for(employee, auth_settings),
        "other_headers": headers_for(other_employee, auth_settings),
        "analyst_headers": headers_for(analyst, auth_settings),
        "admin_headers": headers_for(admin, auth_settings),
        "strong": strong,
        "weak": weak,
    }


def test_employee_alert_review_and_resolution_with_traceability(
    api_client, db_session, integrated_setup
):
    setup = integrated_setup
    employee = setup["employee_headers"]
    analyst = setup["analyst_headers"]
    admin = setup["admin_headers"]

    assert api_client.get("/api/notifications", headers=employee).json() == []
    ingested = api_client.post(
        "/api/automation/emails", json=setup["strong"], headers=setup["automation"]
    )
    assert ingested.status_code == 201
    email = ingested.json()["email"]
    assert [row["id"] for row in api_client.get("/api/emails", headers=employee).json()] == [
        email["id"]
    ]
    assert api_client.get(f"/api/emails/{email['id']}", headers=employee).status_code == 200

    analyzed = api_client.post(
        f"/api/automation/emails/{email['id']}/analyze", headers=setup["automation"]
    )
    assert analyzed.status_code == 200
    result = analyzed.json()
    analysis, alert_id = result["analysis"], result["alert_id"]
    assert analysis["status"] == "COMPLETED" and analysis["risk_score"] >= 70
    assert alert_id is not None

    # The mailbox owner and the active security team receive one in-app notice.
    [notice] = api_client.get("/api/notifications", headers=employee).json()
    assert notice["alert_id"] == alert_id
    assert notice["subject"] == setup["strong"]["subject"]
    assert notice["risk_score"] == analysis["risk_score"]
    assert notice["alert_status"] == "OPEN" and notice["read_at"] is None
    assert "body_text" not in notice
    assert api_client.get("/api/notifications/unread-count", headers=employee).json() == {
        "count": 1
    }
    assert len(api_client.get("/api/notifications", headers=analyst).json()) == 1
    assert len(api_client.get("/api/notifications", headers=admin).json()) == 1

    # Another employee sees neither the mail, the alert nor the notice.
    other = setup["other_headers"]
    assert api_client.get("/api/notifications", headers=other).json() == []
    assert api_client.get("/api/alerts", headers=other).json() == []
    assert api_client.get(f"/api/alerts/{alert_id}", headers=other).status_code == 404
    assert api_client.get(f"/api/emails/{email['id']}", headers=other).status_code == 404

    # The owner can follow the case but cannot perform HITL.
    own_alerts = api_client.get("/api/alerts", headers=employee).json()
    assert [row["id"] for row in own_alerts] == [alert_id]
    assert api_client.get(f"/api/alerts/{alert_id}", headers=employee).status_code == 200
    assert api_client.post(f"/api/alerts/{alert_id}/claim", headers=employee).status_code == 403
    assert (
        api_client.post(
            f"/api/alerts/{alert_id}/resolve",
            headers=employee,
            json={"verdict": "FALSE_POSITIVE", "resolution": "No autorizado"},
        ).status_code
        == 403
    )

    # The analyst finds the alert in the queue, opens the related mail and reviews it.
    queue = api_client.get("/api/alerts?status=OPEN", headers=analyst).json()
    assert [row["id"] for row in queue] == [alert_id]
    assert queue[0]["owner_name"] == setup["employee"].name
    detail = api_client.get(f"/api/alerts/{alert_id}", headers=analyst).json()
    assert detail["analysis"]["risk_score"] == analysis["risk_score"]
    assert api_client.get(f"/api/emails/{email['id']}", headers=analyst).status_code == 200

    claimed = api_client.post(f"/api/alerts/{alert_id}/claim", headers=analyst)
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "UNDER_REVIEW"
    assert claimed.json()["assigned_to"] == str(setup["analyst"].id)
    resolution = "Verificado por un canal independiente."
    resolved = api_client.post(
        f"/api/alerts/{alert_id}/resolve",
        headers=analyst,
        json={"verdict": "CONFIRMED_BEC", "resolution": f"  {resolution}  "},
    )
    assert resolved.status_code == 200
    closed = resolved.json()
    assert closed["status"] == "CLOSED" and closed["verdict"] == "CONFIRMED_BEC"
    assert closed["resolution"] == resolution

    # The employee sees the updated state in the notice and in the case.
    [notice] = api_client.get("/api/notifications", headers=employee).json()
    assert notice["alert_status"] == "CLOSED"
    own_case = api_client.get(f"/api/alerts/{alert_id}", headers=employee).json()
    assert own_case["status"] == "CLOSED" and own_case["verdict"] == "CONFIRMED_BEC"
    assert api_client.post(f"/api/alerts/{alert_id}/claim", headers=employee).status_code == 403

    # Audit records the full chain with minimal data and the right actors.
    alert_events = api_client.get(
        "/api/audit?resource_type=bec_alert&limit=20", headers=admin
    ).json()
    assert {event["action"] for event in alert_events} == {
        "BEC_ALERT_CREATED",
        "BEC_ALERT_CLAIMED",
        "BEC_ALERT_CONFIRMED",
    }
    by_action = {event["action"]: event for event in alert_events}
    assert by_action["BEC_ALERT_CREATED"]["actor_user_id"] is None
    assert by_action["BEC_ALERT_CREATED"]["actor_role"] is None
    assert by_action["BEC_ALERT_CLAIMED"]["actor_user_id"] == str(setup["analyst"].id)
    assert by_action["BEC_ALERT_CONFIRMED"]["actor_role"] == "ANALYST"
    assert all(event["details"] is None for event in alert_events)
    all_events = api_client.get("/api/audit?limit=50", headers=admin).json()
    assert {
        "EMAIL_INGESTED",
        "EMAIL_ANALYZED",
        "BEC_ALERT_CREATED",
        "BEC_ALERT_CLAIMED",
        "BEC_ALERT_CONFIRMED",
    } <= {event["action"] for event in all_events}
    audit_text = str(all_events)
    assert setup["strong"]["subject"] not in audit_text
    assert setup["strong"]["body_text"] not in audit_text
    assert api_client.get("/api/audit?limit=1", headers=analyst).status_code == 403

    summary = api_client.get("/api/dashboard/summary", headers=analyst).json()
    assert summary["alerts"] == {"open": 0, "under_review": 0, "closed": 1}
    assert summary["verdicts"] == {"confirmed_bec": 1, "false_positive": 0}
    assert summary["emails_total"] == summary["analyses_completed"] == 1
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 1


def test_medium_analysis_stays_out_of_the_alert_queue(
    api_client, db_session, integrated_setup, analysis_stub
):
    setup = integrated_setup
    analysis_stub.score = 100
    ingested = api_client.post(
        "/api/automation/emails", json=setup["weak"], headers=setup["automation"]
    )
    assert ingested.status_code == 201
    email = ingested.json()["email"]

    analyzed = api_client.post(
        f"/api/automation/emails/{email['id']}/analyze", headers=setup["automation"]
    )
    assert analyzed.status_code == 200
    result = analyzed.json()
    assert result["alert_id"] is None
    assert result["analysis"]["status"] == "COMPLETED"
    assert result["analysis"]["risk_level"] == "MEDIUM"
    assert 40 <= result["analysis"]["risk_score"] < 70

    # No alert and no notice exist for MEDIUM, even for the security team.
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
    assert db_session.scalar(select(func.count()).select_from(Notification)) == 0
    for headers in (setup["employee_headers"], setup["analyst_headers"]):
        assert api_client.get("/api/notifications", headers=headers).json() == []
        assert api_client.get("/api/alerts", headers=headers).json() == []

    # The owner can read the completed analysis; outsiders still cannot.
    own = api_client.get(f"/api/emails/{email['id']}/analysis", headers=setup["employee_headers"])
    assert own.status_code == 200 and own.json()["risk_level"] == "MEDIUM"
    assert (
        api_client.get(
            f"/api/emails/{email['id']}/analysis", headers=setup["other_headers"]
        ).status_code
        == 404
    )
    assert (
        api_client.get(f"/api/emails/{email['id']}", headers=setup["analyst_headers"]).status_code
        == 404
    )
