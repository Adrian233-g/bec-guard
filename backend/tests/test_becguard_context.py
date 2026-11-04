import pytest
from sqlalchemy import func, select

from app.models import AuditLog, ExecutiveContact, Role, Vendor
from app.scripts.seed_becguard_context import seed

pytestmark = pytest.mark.integration


def test_fictional_context_is_audited_idempotent_and_preserves_edits(db_session, account):
    account.role = Role.ADMIN
    db_session.commit()
    assert seed(db_session, account) == {
        "executives_created": 4,
        "vendors_created": 4,
        "existing": 0,
    }
    executive = db_session.scalar(
        select(ExecutiveContact).where(ExecutiveContact.email == "mateo.rivas@becguard.com")
    )
    vendor = db_session.scalar(select(Vendor).where(Vendor.domain == "andes-nube.example"))
    assert executive.responsibilities and "PAYMENT_REQUEST" in executive.allowed_actions
    assert vendor.responsibilities and vendor.contact_email
    executive.responsibilities = "Modificación del administrador"
    db_session.commit()
    assert seed(db_session, account) == {
        "executives_created": 0,
        "vendors_created": 0,
        "existing": 8,
    }
    assert executive.responsibilities == "Modificación del administrador"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action.in_(("EXECUTIVE_CREATED", "VENDOR_CREATED")))
        )
        == 8
    )


def test_fictional_context_requires_active_admin(db_session, account):
    account.role = Role.ANALYST
    db_session.commit()
    with pytest.raises(ValueError):
        seed(db_session, account)
    assert db_session.scalar(select(func.count()).select_from(ExecutiveContact)) == 0


def test_context_migration_prevents_discarding_configured_scope(
    db_session, account, migration_runner
):
    from alembic import command

    account.role = Role.ADMIN
    db_session.commit()
    seed(db_session, account)
    with pytest.raises(RuntimeError, match="responsibilities are configured"):
        migration_runner(command.downgrade, "0015_analysis_rules_fallback")
    assert db_session.scalar(select(func.count()).select_from(ExecutiveContact)) == 4
