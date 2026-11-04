from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, load_only

from app.api.dependencies import require_roles
from app.core.database import get_session
from app.models import BECAlert, Email, EmailAnalysis, Mailbox, Role, User
from app.schemas.email import EmailDetailResponse, EmailIngestRequest, EmailSummaryResponse
from app.services.email_ingestion import ingest_email

router = APIRouter(prefix="/api/emails", tags=["Email ingestion"])
Database = Annotated[Session, Depends(get_session)]
AnyUser = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST, Role.EMPLOYEE))]
Reader = AnyUser
Writer = AnyUser


@router.post("", response_model=EmailDetailResponse, status_code=201)
def create_email(body: EmailIngestRequest, session: Database, actor: AnyUser, request: Request):
    if body.mailbox_id is not None:
        mailbox = session.get(Mailbox, body.mailbox_id)
        if mailbox is None or mailbox.user_id != actor.id or mailbox.status != "ACTIVE":
            raise HTTPException(403, "Cannot ingest into a mailbox you do not own")
        target_mailbox_id = body.mailbox_id
    else:
        target_mailbox_id = session.scalar(
            select(Mailbox.id).where(Mailbox.user_id == actor.id, Mailbox.status == "ACTIVE")
        )
        if target_mailbox_id is None:
            raise HTTPException(400, "Active mailbox required for ingestion")

    return ingest_email(
        session,
        body,
        mailbox_id=target_mailbox_id,
        actor=actor,
        peer=request.client.host if request.client else None,
    )


@router.get("", response_model=list[EmailSummaryResponse])
def list_emails(
    session: Database,
    actor: AnyUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Literal["received", "ingested"] = "received",
):
    user_mailboxes = select(Mailbox.id).where(Mailbox.user_id == actor.id)
    statement = (
        select(Email)
        .where(Email.mailbox_id.in_(user_mailboxes))
        .options(
            load_only(
                Email.id,
                Email.mailbox_id,
                Email.message_id,
                Email.sender_name,
                Email.sender_email,
                Email.reply_to,
                Email.subject,
                Email.received_at,
                Email.ingested_at,
            )
        )
        .order_by(
            Email.ingested_at.desc() if order == "ingested" else Email.received_at.desc(),
            Email.id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


@router.get("/{email_id}", response_model=EmailDetailResponse)
def get_email(email_id: UUID, session: Database, actor: AnyUser):
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(404, "Email not found")

    is_owner = session.scalar(
        select(
            exists(
                select(1).where(
                    Mailbox.id == email.mailbox_id,
                    Mailbox.user_id == actor.id,
                )
            )
        )
    )
    if is_owner:
        return email

    if actor.role in (Role.ADMIN, Role.ANALYST):
        has_alert = session.scalar(
            select(
                exists(
                    select(1)
                    .select_from(BECAlert)
                    .join(EmailAnalysis, BECAlert.analysis_id == EmailAnalysis.id)
                    .where(EmailAnalysis.email_id == email.id)
                )
            )
        )
        if has_alert:
            return email

    raise HTTPException(404, "Email not found")
