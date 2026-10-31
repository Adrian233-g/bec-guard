from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.identity import normalize_email
from app.models import Mailbox, Role, User
from app.services.audit import AuditAction, record_mailbox_event


def create_mailbox(
    session: Session,
    *,
    user_id: UUID,
    email_address: str,
    provider: str = "gmail",
    actor: User,
    peer: str | None = None,
) -> Mailbox:
    # In this phase, each user can register at most one mailbox.
    existing_user_mailbox = session.scalar(select(Mailbox.id).where(Mailbox.user_id == user_id))
    if existing_user_mailbox is not None:
        raise HTTPException(409, "User already has a registered mailbox")

    normalized_email = normalize_email(email_address)
    existing_email_mailbox = session.scalar(
        select(Mailbox.id).where(func.lower(Mailbox.email_address) == func.lower(normalized_email))
    )
    if existing_email_mailbox is not None:
        raise HTTPException(409, "Email address is already registered as a mailbox")

    mailbox = Mailbox(
        user_id=user_id,
        email_address=normalized_email,
        provider=provider,
        status="ACTIVE",
    )
    session.add(mailbox)
    try:
        session.flush()
        record_mailbox_event(
            session,
            AuditAction.MAILBOX_CREATED,
            actor=actor,
            mailbox_id=mailbox.id,
            peer=peer,
        )
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        if isinstance(error, IntegrityError):
            raise HTTPException(409, "Conflict creating mailbox") from None
        raise
    return mailbox


def get_user_mailboxes(session: Session, user_id: UUID) -> list[Mailbox]:
    statement = (
        select(Mailbox)
        .where(Mailbox.user_id == user_id)
        .order_by(Mailbox.created_at.desc(), Mailbox.id)
    )
    return list(session.scalars(statement))


def get_mailbox(session: Session, mailbox_id: UUID) -> Mailbox | None:
    return session.get(Mailbox, mailbox_id)


def update_mailbox_status(
    session: Session,
    *,
    mailbox_id: UUID,
    status: str,
    actor: User,
    peer: str | None = None,
) -> Mailbox:
    mailbox = session.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(404, "Mailbox not found")
    if mailbox.user_id != actor.id and actor.role != Role.ADMIN:
        raise HTTPException(403, "Forbidden")

    mailbox.status = status
    action = (
        AuditAction.MAILBOX_DISCONNECTED
        if status == "DISCONNECTED"
        else AuditAction.MAILBOX_UPDATED
    )
    try:
        session.flush()
        record_mailbox_event(
            session,
            action,
            actor=actor,
            mailbox_id=mailbox.id,
            peer=peer,
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    return mailbox
