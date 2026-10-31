import pytest
from alembic import command
from sqlalchemy import inspect, select

from app.models import Mailbox
from app.services.mailbox_connections import (
    ConnectionProgressError,
    advance_connection,
    mark_connection_uncertain,
    start_connection,
)

pytestmark = pytest.mark.integration


def test_checkpoints_are_ordered_non_secret_and_fail_closed(db_session, account, migrated_engine):
    mailbox = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
    state = start_connection(
        db_session,
        mailbox_id=mailbox.id,
        imap_credential_id="imap01",
        automation_credential_id="auth01",
    )
    db_session.commit()
    with pytest.raises(ConnectionProgressError, match="transition"):
        advance_connection(
            db_session, mailbox_id=mailbox.id, expected_stage="allocated", next_stage="active"
        )
    for current, target in [
        ("allocated", "imap-created"),
        ("imap-created", "imap-verified"),
        ("imap-verified", "automation-created"),
    ]:
        advance_connection(
            db_session, mailbox_id=mailbox.id, expected_stage=current, next_stage=target
        )
        db_session.commit()
    with pytest.raises(ConnectionProgressError, match="Workflow identifier"):
        advance_connection(
            db_session,
            mailbox_id=mailbox.id,
            expected_stage="automation-created",
            next_stage="workflow-created",
        )
    advance_connection(
        db_session,
        mailbox_id=mailbox.id,
        expected_stage="automation-created",
        next_stage="workflow-created",
        workflow_id="wf01",
    )
    db_session.commit()
    mark_connection_uncertain(db_session, mailbox_id=mailbox.id)
    db_session.commit()
    with pytest.raises(ConnectionProgressError, match="reconciliation"):
        advance_connection(
            db_session,
            mailbox_id=mailbox.id,
            expected_stage="workflow-created",
            next_stage="active",
        )
    assert state.workflow_id == "wf01"
    assert state.needs_reconciliation is True
    columns = {col["name"] for col in inspect(migrated_engine).get_columns("mailbox_connections")}
    assert not any("password" in name or "secret" in name or "token" in name for name in columns)


def test_downgrade_refuses_to_discard_remote_resource_identifiers(
    db_session, account, migration_runner
):
    mailbox = db_session.scalar(select(Mailbox).where(Mailbox.user_id == account.id))
    start_connection(
        db_session,
        mailbox_id=mailbox.id,
        imap_credential_id="imap01",
        automation_credential_id="auth01",
    )
    db_session.commit()
    with pytest.raises(RuntimeError, match="connection records exist"):
        migration_runner(command.downgrade, "0011_mailbox_verification")
