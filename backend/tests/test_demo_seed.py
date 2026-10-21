from collections import Counter
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, BECAlert, Email, EmailAnalysis, ExecutiveContact, Role, Vendor
from app.scripts.seed_demo import main, seed_demo


@pytest.mark.integration
def test_seed_creates_audited_context_and_unanalysed_emails(db_session, account):
    account.role = Role.ADMIN
    db_session.commit()
    result = seed_demo(db_session, actor=account)
    assert result == {
        "executives": {"created": 2, "existing": 0},
        "vendors": {"created": 2, "existing": 0},
        "emails": {"created": 12, "existing": 0},
    }
    assert db_session.scalar(select(func.count()).select_from(EmailAnalysis)) == 0
    assert db_session.scalar(select(func.count()).select_from(BECAlert)) == 0
    events = list(db_session.scalars(select(AuditLog)))
    assert Counter(e.action for e in events) == {
        "EXECUTIVE_CREATED": 2,
        "VENDOR_CREATED": 2,
        "EMAIL_INGESTED": 12,
    }
    assert all(e.actor_user_id == account.id and e.actor_role == Role.ADMIN for e in events)
    assert all(e.details is None for e in events)
    assert all(e.subject.startswith("[DEMO ") for e in db_session.scalars(select(Email)))


@pytest.mark.integration
def test_seed_is_repeatable_without_overwriting_edits_or_analysis(db_session, account):
    account.role = Role.ADMIN
    db_session.commit()
    seed_demo(db_session, actor=account)
    mail = db_session.scalars(select(Email).order_by(Email.message_id)).first()
    executive = db_session.scalars(select(ExecutiveContact)).first()
    vendor = db_session.scalars(select(Vendor)).first()
    mail.body_text = "Operator edited this message."
    executive.is_active = False
    vendor.contact_email = "operator@changed.example"
    analysis = EmailAnalysis(
        email_id=mail.id,
        status="ERROR",
        deterministic_score=0,
        signals=[],
        policy_version="det-v1/semantic-v1/hybrid-v1",
        error_code="LLM_NOT_CONFIGURED",
        analyzed_at=datetime.now(UTC),
    )
    db_session.add(analysis)
    db_session.commit()
    ids = set(db_session.scalars(select(Email.id)))
    result = seed_demo(db_session, actor=account)
    assert result == {
        "executives": {"created": 0, "existing": 2},
        "vendors": {"created": 0, "existing": 2},
        "emails": {"created": 0, "existing": 12},
    }
    assert set(db_session.scalars(select(Email.id))) == ids
    db_session.refresh(mail)
    db_session.refresh(executive)
    db_session.refresh(vendor)
    assert mail.body_text == "Operator edited this message."
    assert not executive.is_active
    assert vendor.contact_email == "operator@changed.example"
    assert db_session.scalar(select(EmailAnalysis.id)) == analysis.id
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 16


@pytest.mark.integration
@pytest.mark.parametrize(
    "role,active",
    [
        (Role.ANALYST, True),
        (Role.MANAGER, True),
        (Role.AUDITOR, True),
        (Role.ADMIN, False),
    ],
)
def test_seed_requires_an_active_admin(db_session, account, role, active):
    account.role, account.is_active = role, active
    db_session.commit()
    with pytest.raises(ValueError, match="active ADMIN"):
        seed_demo(db_session, actor=account)
    assert db_session.scalar(select(func.count()).select_from(Email)) == 0
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_seed_cli_requires_confirmation_before_database_access(monkeypatch):
    def unexpected_engine(*_args, **_kwargs):
        pytest.fail("Database must not be accessed without explicit demo confirmation")

    monkeypatch.setattr("app.scripts.seed_demo.create_database_engine", unexpected_engine)
    with pytest.raises(SystemExit) as error:
        main(["--actor-email", "admin@operator.example"])
    assert error.value.code == 2
