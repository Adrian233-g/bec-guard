"""Owner-scoped mailbox lifecycle; every remote operation fails closed."""

import secrets
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.connector_tokens import connector_token
from app.models import Mailbox, MailboxConnection, User
from app.services.audit import AuditAction, record_mailbox_event
from app.services.gmail_verification import (
    GmailAuthenticationFailed,
    GmailUnavailable,
    verify_gmail_access,
)
from app.services.mailbox_connections import start_connection
from app.services.n8n_mailboxes import N8nMailboxClient, N8nUnavailable


def _owner_mailbox(session: Session, actor: User, mailbox_id: UUID) -> Mailbox:
    mailbox = session.scalar(select(Mailbox).where(Mailbox.id == mailbox_id).with_for_update())
    if mailbox is None or mailbox.user_id != actor.id:
        raise HTTPException(404, "Mailbox not found")
    return mailbox


def connect_mailbox(
    session: Session,
    *,
    actor: User,
    mailbox_id: UUID,
    app_password: str,
    client: N8nMailboxClient,
    master_key: str,
    peer: str | None,
) -> Mailbox:
    if len(master_key) < 32:
        raise HTTPException(503, "Mailbox connections unavailable")
    mailbox = _owner_mailbox(session, actor, mailbox_id)
    if mailbox.provider != "gmail":
        raise HTTPException(400, "Gmail mailbox required")
    if mailbox.status not in {"PENDING", "DISCONNECTED"}:
        raise HTTPException(409, "Mailbox cannot be connected")
    if session.scalar(
        select(Mailbox.id).where(
            Mailbox.id != mailbox_id,
            func.lower(Mailbox.email_address) == func.lower(mailbox.email_address),
            Mailbox.status == "ACTIVE",
        )
    ):
        raise HTTPException(409, "Mailbox address is already connected")
    if session.scalar(
        select(MailboxConnection.id).where(MailboxConnection.mailbox_id == mailbox_id)
    ):
        raise HTTPException(409, "Existing connection requires review")
    # Validate before storing any n8n resources. Keep no credentials in the DB.
    try:
        client.workflow(mailbox_id, "placeholder1", "placeholder2")
        verify_gmail_access(mailbox.email_address, app_password)
    except GmailAuthenticationFailed:
        raise HTTPException(400, "Gmail authentication failed") from None
    except GmailUnavailable, N8nUnavailable:
        raise HTTPException(503, "Mailbox connections unavailable") from None

    connection = start_connection(
        session,
        mailbox_id=mailbox_id,
        imap_credential_id=secrets.token_urlsafe(12),
        automation_credential_id=secrets.token_urlsafe(12),
    )
    connection.needs_reconciliation = True
    session.commit()
    identity = mailbox_id.hex
    try:
        result = client.request(
            "POST",
            "/credentials",
            {
                "id": connection.imap_credential_id,
                "name": f"BEC Guard IMAP {identity}",
                "type": "imap",
                "data": {
                    "user": mailbox.email_address,
                    "password": app_password.replace(" ", ""),
                    "host": "imap.gmail.com",
                    "port": 993,
                    "secure": True,
                    "allowUnauthorizedCerts": False,
                },
            },
        )
        if result.get("id") != connection.imap_credential_id:
            raise N8nUnavailable("Unexpected credential id")
        connection.stage = "imap-created"
        session.commit()
        result = client.request("POST", f"/credentials/{connection.imap_credential_id}/test")
        if result.get("status") != "OK":
            raise N8nUnavailable("Credential test failed")
        connection.stage = "imap-verified"
        session.commit()
        result = client.request(
            "POST",
            "/credentials",
            {
                "id": connection.automation_credential_id,
                "name": f"BEC Guard connector {identity}",
                "type": "httpHeaderAuth",
                "data": {
                    "name": "X-BEC-Automation-Key",
                    "value": connector_token(master_key, mailbox_id, connection.id),
                },
            },
        )
        if result.get("id") != connection.automation_credential_id:
            raise N8nUnavailable("Unexpected credential id")
        connection.stage = "automation-created"
        session.commit()
        result = client.request(
            "POST",
            "/workflows",
            client.workflow(
                mailbox_id, connection.imap_credential_id, connection.automation_credential_id
            ),
        )
        workflow_id = result.get("id")
        if (
            not isinstance(workflow_id, str)
            or not workflow_id.isascii()
            or not all(char.isalnum() or char in "_-" for char in workflow_id)
            or not 1 <= len(workflow_id) <= 128
        ):
            raise N8nUnavailable("Invalid workflow id")
        connection.workflow_id = workflow_id
        connection.stage = "workflow-created"
        session.commit()
        session.refresh(actor)
        if not actor.is_active:
            raise N8nUnavailable("User unavailable")
        client.request("POST", f"/workflows/{workflow_id}/publish")
        # Events received before this commit are rejected, because activation is
        # not confirmed yet. The UID startup boundary remains per receiver.
        mailbox.status = "ACTIVE"
        connection.stage = "active"
        connection.needs_reconciliation = False
        record_mailbox_event(
            session, AuditAction.MAILBOX_UPDATED, actor=actor, mailbox_id=mailbox.id, peer=peer
        )
        session.commit()
        return mailbox
    except N8nUnavailable, IntegrityError:
        session.rollback()
        # The connection was committed before the first remote call. It remains
        # quarantined, including on crashes or lost responses; do not auto-retry.
        raise HTTPException(503, "Mailbox setup requires review") from None


def disconnect_mailbox(
    session: Session, *, actor: User, mailbox_id: UUID, client: N8nMailboxClient, peer: str | None
) -> Mailbox:
    mailbox = _owner_mailbox(session, actor, mailbox_id)
    connection = session.scalar(
        select(MailboxConnection)
        .where(MailboxConnection.mailbox_id == mailbox_id)
        .with_for_update()
    )
    if connection is None or connection.stage != "active" or connection.needs_reconciliation:
        raise HTTPException(409, "Connection requires review")
    if not connection.workflow_id:
        raise HTTPException(409, "Connection requires review")
    # Disable backend access before calling n8n so a slow or failed unpublish is safe.
    connection.needs_reconciliation = True
    mailbox.status = "DISCONNECTED"
    record_mailbox_event(
        session, AuditAction.MAILBOX_DISCONNECTED, actor=actor, mailbox_id=mailbox.id, peer=peer
    )
    session.commit()
    try:
        client.request("POST", f"/workflows/{connection.workflow_id}/unpublish")
        connection.stage = "workflow-unpublished"
        session.commit()
        client.request("DELETE", f"/workflows/{connection.workflow_id}")
        connection.stage = "workflow-deleted"
        session.commit()
        client.request("DELETE", f"/credentials/{connection.imap_credential_id}")
        connection.stage = "imap-deleted"
        session.commit()
        client.request("DELETE", f"/credentials/{connection.automation_credential_id}")
        connection.stage = "automation-deleted"
        session.commit()
        session.delete(connection)
        session.commit()
        return mailbox
    except N8nUnavailable:
        session.rollback()
        raise HTTPException(503, "Mailbox disconnection requires review") from None
