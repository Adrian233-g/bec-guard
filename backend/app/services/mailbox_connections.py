"""Persist non-secret, strictly ordered steps of mailbox provisioning.

Transactions belong to the caller, which must commit a checkpoint before each
subsequent network call. An uncertain remote result blocks automatic progress.
"""

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MailboxConnection

TRANSITIONS = {
    "allocated": "imap-created",
    "imap-created": "imap-verified",
    "imap-verified": "automation-created",
    "automation-created": "workflow-created",
    "workflow-created": "active",
    "active": "workflow-unpublished",
    "workflow-unpublished": "workflow-deleted",
    "workflow-deleted": "imap-deleted",
    "imap-deleted": "automation-deleted",
}


class ConnectionProgressError(Exception):
    pass


def _valid_id(value: str, length: int) -> bool:
    return bool(re.fullmatch(rf"[A-Za-z0-9_-]{{1,{length}}}", value))


def start_connection(
    session: Session, *, mailbox_id: UUID, imap_credential_id: str, automation_credential_id: str
) -> MailboxConnection:
    if not _valid_id(imap_credential_id, 16) or not _valid_id(automation_credential_id, 16):
        raise ConnectionProgressError("Invalid credential identifiers")
    if imap_credential_id == automation_credential_id:
        raise ConnectionProgressError("Credential identifiers must be distinct")
    connection = MailboxConnection(
        mailbox_id=mailbox_id,
        stage="allocated",
        imap_credential_id=imap_credential_id,
        automation_credential_id=automation_credential_id,
        needs_reconciliation=False,
    )
    session.add(connection)
    session.flush()
    return connection


def _locked(session: Session, mailbox_id: UUID) -> MailboxConnection:
    connection = session.scalar(
        select(MailboxConnection)
        .where(MailboxConnection.mailbox_id == mailbox_id)
        .with_for_update()
    )
    if connection is None:
        raise ConnectionProgressError("Connection not found")
    return connection


def advance_connection(
    session: Session,
    *,
    mailbox_id: UUID,
    expected_stage: str,
    next_stage: str,
    workflow_id: str | None = None,
) -> MailboxConnection:
    connection = _locked(session, mailbox_id)
    if connection.needs_reconciliation:
        raise ConnectionProgressError("Connection requires reconciliation")
    if connection.stage != expected_stage or TRANSITIONS.get(expected_stage) != next_stage:
        raise ConnectionProgressError("Invalid connection transition")
    if next_stage == "workflow-created":
        if not workflow_id or not _valid_id(workflow_id, 128):
            raise ConnectionProgressError("Workflow identifier required")
        connection.workflow_id = workflow_id
    elif workflow_id is not None:
        raise ConnectionProgressError("Unexpected workflow identifier")
    connection.stage = next_stage
    session.flush()
    return connection


def mark_connection_uncertain(session: Session, *, mailbox_id: UUID) -> MailboxConnection:
    connection = _locked(session, mailbox_id)
    connection.needs_reconciliation = True
    session.flush()
    return connection
