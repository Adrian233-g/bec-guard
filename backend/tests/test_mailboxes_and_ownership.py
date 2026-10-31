from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.tokens import create_access_token
from app.models import BECAlert, Email, EmailAnalysis, Mailbox, Role, User
from app.models.enums import AlertStatus, AnalysisStatus, BECType, RiskLevel
from app.schemas.email import EmailIngestRequest
from app.services.email_ingestion import ingest_email_idempotently

pytestmark = pytest.mark.integration


def make_user(session, name: str, email: str, role: Role) -> User:
    user = User(
        name=name,
        email=email,
        password_hash="test-hash-value-12345",
        role=role,
    )
    session.add(user)
    session.commit()
    return user


def auth_header(user: User, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


def test_mailbox_crud_and_uniqueness(api_client, db_session, auth_settings):
    user1 = make_user(db_session, "Emp One", "emp1@example.com", Role.EMPLOYEE)
    user2 = make_user(db_session, "Emp Two", "emp2@example.com", Role.EMPLOYEE)
    h1 = auth_header(user1, auth_settings)
    h2 = auth_header(user2, auth_settings)

    # 1. User 1 creates mailbox
    resp = api_client.post(
        "/api/mailboxes",
        json={"email_address": "emp1.inbox@example.com", "provider": "gmail"},
        headers=h1,
    )
    assert resp.status_code == 201
    data1 = resp.json()
    assert data1["email_address"] == "emp1.inbox@example.com"
    assert data1["status"] == "PENDING"
    mb1_id = UUID(data1["id"])

    # 2. User 1 lists mailboxes
    resp = api_client.get("/api/mailboxes", headers=h1)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == str(mb1_id)

    # 3. User 2 lists mailboxes -> empty
    resp = api_client.get("/api/mailboxes", headers=h2)
    assert resp.status_code == 200
    assert resp.json() == []

    # 4. User 1 cannot create a second mailbox (enforces 1 per user)
    resp = api_client.post(
        "/api/mailboxes",
        json={"email_address": "another@example.com", "provider": "gmail"},
        headers=h1,
    )
    assert resp.status_code == 409
    assert "already has a registered mailbox" in resp.text

    # 5. A pending, unverified claim cannot reserve an address from another user.
    resp = api_client.post(
        "/api/mailboxes",
        json={"email_address": "EMP1.INBOX@example.com", "provider": "gmail"},
        headers=h2,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "PENDING"

    # 6. User 1 disconnects their mailbox
    resp = api_client.patch(
        f"/api/mailboxes/{mb1_id}",
        json={"status": "DISCONNECTED"},
        headers=h1,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "DISCONNECTED"


def test_multitenant_email_isolation_and_idempotency(api_client, db_session, auth_settings):
    emp1 = make_user(db_session, "Alice", "alice@example.com", Role.EMPLOYEE)
    emp2 = make_user(db_session, "Bob", "bob@example.com", Role.EMPLOYEE)
    h1 = auth_header(emp1, auth_settings)
    h2 = auth_header(emp2, auth_settings)

    # Create mailbox for Alice
    mb1 = Mailbox(
        user_id=emp1.id, email_address="alice@example.com", provider="gmail", status="ACTIVE"
    )
    # Create mailbox for Bob
    mb2 = Mailbox(
        user_id=emp2.id, email_address="bob@example.com", provider="gmail", status="ACTIVE"
    )
    db_session.add_all([mb1, mb2])
    db_session.commit()

    shared_msg_id = "<shared-broadcast-001@vendor.example>"
    base_payload = {
        "message_id": shared_msg_id,
        "sender_email": "billing@vendor.example",
        "sender_name": "Vendor Billing",
        "subject": "Monthly Statement",
        "body_text": "Here is the monthly statement for your records.",
        "received_at": datetime(2026, 10, 31, 12, 0, tzinfo=UTC).isoformat(),
    }

    # Ingest for Alice
    req1 = EmailIngestRequest(**{**base_payload, "to_recipients": ["alice@example.com"]})
    email1, created1 = ingest_email_idempotently(db_session, req1, mailbox_id=mb1.id)
    assert created1 is True

    # Ingest for Bob with the SAME Message-ID
    req2 = EmailIngestRequest(**{**base_payload, "to_recipients": ["bob@example.com"]})
    email2, created2 = ingest_email_idempotently(db_session, req2, mailbox_id=mb2.id)
    assert created2 is True
    assert email1.id != email2.id
    assert email1.message_id == email2.message_id

    # Ingest again for Alice -> idempotent, returns existing
    email1_repeat, created_repeat = ingest_email_idempotently(db_session, req1, mailbox_id=mb1.id)
    assert created_repeat is False
    assert email1_repeat.id == email1.id

    # Alice lists emails: sees only her own
    resp1 = api_client.get("/api/emails", headers=h1)
    assert resp1.status_code == 200
    items1 = resp1.json()
    assert len(items1) == 1
    assert items1[0]["id"] == str(email1.id)

    # Bob lists emails: sees only his own
    resp2 = api_client.get("/api/emails", headers=h2)
    assert resp2.status_code == 200
    items2 = resp2.json()
    assert len(items2) == 1
    assert items2[0]["id"] == str(email2.id)

    # Alice cannot read Bob's email directly by UUID
    resp_cross1 = api_client.get(f"/api/emails/{email2.id}", headers=h1)
    assert resp_cross1.status_code == 404

    # Bob cannot read Alice's email directly by UUID
    resp_cross2 = api_client.get(f"/api/emails/{email1.id}", headers=h2)
    assert resp_cross2.status_code == 404


def test_alert_investigation_exception_for_analyst_and_admin(api_client, db_session, auth_settings):
    emp = make_user(db_session, "Victim", "victim@example.com", Role.EMPLOYEE)
    analyst = make_user(db_session, "Analyst", "analyst@example.com", Role.ANALYST)
    admin = make_user(db_session, "Admin", "admin@example.com", Role.ADMIN)
    other_emp = make_user(db_session, "Other", "other@example.com", Role.EMPLOYEE)

    h_emp = auth_header(emp, auth_settings)
    h_analyst = auth_header(analyst, auth_settings)
    h_admin = auth_header(admin, auth_settings)
    h_other = auth_header(other_emp, auth_settings)

    mb = Mailbox(
        user_id=emp.id, email_address="victim@example.com", provider="gmail", status="ACTIVE"
    )
    db_session.add(mb)
    db_session.commit()

    # Normal email with no alert
    email_normal = Email(
        mailbox_id=mb.id,
        message_id="<normal-1@example.com>",
        sender_email="colleague@example.com",
        to_recipients=["victim@example.com"],
        cc_recipients=[],
        subject="Lunch plans",
        body_text="Are we having lunch at noon?",
        received_at=datetime(2026, 10, 31, 10, 0, tzinfo=UTC),
    )
    # Suspicious email that gets an alert
    email_suspicious = Email(
        mailbox_id=mb.id,
        message_id="<phish-1@example.com>",
        sender_email="ceo-fake@spoofed.example",
        to_recipients=["victim@example.com"],
        cc_recipients=[],
        subject="URGENT WIRE TRANSFER",
        body_text="Wire 50,000 USD immediately to this new bank account.",
        received_at=datetime(2026, 10, 31, 11, 0, tzinfo=UTC),
    )
    db_session.add_all([email_normal, email_suspicious])
    db_session.commit()

    # Create analysis and alert for email_suspicious
    analysis = EmailAnalysis(
        email_id=email_suspicious.id,
        status=AnalysisStatus.COMPLETED,
        deterministic_score=85,
        semantic_score=90,
        risk_score=88,
        risk_level=RiskLevel.CRITICAL,
        bec_type=BECType.EXECUTIVE_IMPERSONATION,
        signals=[{"code": "URGENCY", "description": "Urgent request", "source": "SEMANTIC"}],
        summary="Executive impersonation demanding funds",
        recommended_action="Do not transfer funds; contact CEO out of band",
        provider="google",
        model="gemini-3.5-flash-lite",
        policy_version="v1",
        analyzed_at=datetime(2026, 10, 31, 11, 5, tzinfo=UTC),
    )
    db_session.add(analysis)
    db_session.commit()

    alert = BECAlert(
        analysis_id=analysis.id,
        status=AlertStatus.OPEN,
    )
    db_session.add(alert)
    db_session.commit()

    # 1. Normal email has NO alert:
    # Analyst cannot view victim's normal email
    assert api_client.get(f"/api/emails/{email_normal.id}", headers=h_analyst).status_code == 404
    # Admin cannot view victim's normal email
    assert api_client.get(f"/api/emails/{email_normal.id}", headers=h_admin).status_code == 404
    # Victim can view their own normal email
    assert api_client.get(f"/api/emails/{email_normal.id}", headers=h_emp).status_code == 200

    # 2. Suspicious email HAS an alert:
    # Analyst CAN view suspicious email because of the alert exception!
    resp_analyst = api_client.get(f"/api/emails/{email_suspicious.id}", headers=h_analyst)
    assert resp_analyst.status_code == 200
    assert resp_analyst.json()["id"] == str(email_suspicious.id)

    # Admin CAN view suspicious email because of the alert exception!
    resp_admin = api_client.get(f"/api/emails/{email_suspicious.id}", headers=h_admin)
    assert resp_admin.status_code == 200

    # 3. Alerts queue isolation:
    # Analyst sees the alert in queue, along with mailbox owner info
    resp_queue = api_client.get("/api/alerts", headers=h_analyst)
    assert resp_queue.status_code == 200
    alerts_data = resp_queue.json()
    assert len(alerts_data) == 1
    assert alerts_data[0]["id"] == str(alert.id)
    assert alerts_data[0]["mailbox_email"] == "victim@example.com"
    assert alerts_data[0]["owner_name"] == "Victim"

    # Victim sees their own alert in queue
    resp_victim = api_client.get("/api/alerts", headers=h_emp)
    assert resp_victim.status_code == 200
    assert len(resp_victim.json()) == 1
    assert resp_victim.json()[0]["id"] == str(alert.id)

    # Other employee DOES NOT see victim's alert
    resp_other = api_client.get("/api/alerts", headers=h_other)
    assert resp_other.status_code == 200
    assert resp_other.json() == []

    # Victim cannot claim or resolve alert (403)
    assert api_client.post(f"/api/alerts/{alert.id}/claim", headers=h_emp).status_code == 403
    assert (
        api_client.post(
            f"/api/alerts/{alert.id}/resolve",
            json={"verdict": "CONFIRMED_BEC", "resolution": "Confirmed scam"},
            headers=h_emp,
        ).status_code
        == 403
    )

    # Analyst can claim alert
    resp_claim = api_client.post(f"/api/alerts/{alert.id}/claim", headers=h_analyst)
    assert resp_claim.status_code == 200
    assert resp_claim.json()["status"] == "UNDER_REVIEW"


def test_empty_mailbox_patch_cannot_expose_other_users_metadata(
    api_client, db_session, auth_settings
):
    owner = make_user(db_session, "Owner", "owner-meta@example.com", Role.EMPLOYEE)
    other = make_user(db_session, "Other", "other-meta@example.com", Role.EMPLOYEE)
    mailbox = Mailbox(
        user_id=owner.id, email_address="private@example.com", provider="gmail", status="PENDING"
    )
    db_session.add(mailbox)
    db_session.commit()
    headers = auth_header(other, auth_settings)
    for body in ({}, {"status": None}):
        response = api_client.patch(f"/api/mailboxes/{mailbox.id}", json=body, headers=headers)
        assert response.status_code == 400
        assert "private@example.com" not in response.text
    assert api_client.get(f"/api/mailboxes/{mailbox.id}", headers=headers).status_code == 404
    assert (
        api_client.patch(
            f"/api/mailboxes/{mailbox.id}", json={"status": "DISCONNECTED"}, headers=headers
        ).status_code
        == 404
    )
