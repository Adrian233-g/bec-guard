from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Email, User
from app.schemas.email import EmailIngestRequest
from app.services.audit import record_email_ingested


def ingest_email(
    session: Session,
    data: EmailIngestRequest,
    *,
    mailbox_id: UUID | None = None,
    actor: User | None,
    peer: str | None = None,
) -> Email:
    target_mailbox_id = mailbox_id or data.mailbox_id
    if target_mailbox_id is None:
        raise ValueError("mailbox_id is required for ingestion")
    dump = data.model_dump()
    dump["mailbox_id"] = target_mailbox_id
    email = Email(**dump)
    session.add(email)
    try:
        session.flush()
        record_email_ingested(session, actor=actor, email_id=email.id, peer=peer)
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        if (
            isinstance(error, IntegrityError)
            and getattr(error.orig, "sqlstate", None) == "23505"
            and getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            in ("uq_emails_mailbox_message_id", "uq_emails_message_id")
        ):
            raise HTTPException(409, "Message-ID already exists for this mailbox") from None
        raise
    return email


def ingest_email_idempotently(
    session: Session,
    data: EmailIngestRequest,
    *,
    mailbox_id: UUID | None = None,
    peer: str | None = None,
) -> tuple[Email, bool]:
    target_mailbox_id = mailbox_id or data.mailbox_id
    if target_mailbox_id is None:
        raise ValueError("mailbox_id is required for ingestion")
    statement = select(Email).where(
        Email.mailbox_id == target_mailbox_id,
        Email.message_id == data.message_id,
    )
    existing = session.scalar(statement)
    if existing is not None:
        return existing, False
    try:
        return (
            ingest_email(session, data, mailbox_id=target_mailbox_id, actor=None, peer=peer),
            True,
        )
    except HTTPException as error:
        if error.status_code != 409:
            raise
        # Another transaction won the UNIQUE (mailbox_id, Message-ID) race.
        # ingest_email has rolled back; READ COMMITTED can now see the committed winner.
        return session.execute(statement).scalar_one(), False
