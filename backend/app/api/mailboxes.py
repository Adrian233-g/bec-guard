from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.mailbox import (
    GmailVerificationRequest,
    GmailVerificationResponse,
    MailboxCreate,
    MailboxResponse,
    MailboxUpdate,
)
from app.services.gmail_verification import (
    GmailAuthenticationFailed,
    GmailUnavailable,
    verify_gmail_access,
)
from app.services.mailboxes import (
    create_mailbox,
    get_mailbox,
    get_user_mailboxes,
    update_mailbox_status,
)

router = APIRouter(prefix="/api/mailboxes", tags=["Mailboxes"])
Database = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[MailboxResponse])
def list_my_mailboxes(session: Database, actor: CurrentUser):
    return get_user_mailboxes(session, actor.id)


@router.post("", response_model=MailboxResponse, status_code=201)
def register_mailbox(body: MailboxCreate, session: Database, actor: CurrentUser, request: Request):
    return create_mailbox(
        session,
        user_id=actor.id,
        email_address=body.email_address,
        provider=body.provider.value if hasattr(body.provider, "value") else str(body.provider),
        actor=actor,
        peer=request.client.host if request.client else None,
    )


@router.get("/{mailbox_id}", response_model=MailboxResponse)
def get_single_mailbox(mailbox_id: UUID, session: Database, actor: CurrentUser):
    mailbox = get_mailbox(session, mailbox_id)
    if mailbox is None:
        raise HTTPException(404, "Mailbox not found")
    if mailbox.user_id != actor.id and actor.role != "ADMIN":
        raise HTTPException(404, "Mailbox not found")
    return mailbox


@router.patch("/{mailbox_id}", response_model=MailboxResponse)
def update_single_mailbox(
    mailbox_id: UUID,
    body: MailboxUpdate,
    session: Database,
    actor: CurrentUser,
    request: Request,
):
    status_val = body.status.value if hasattr(body.status, "value") else str(body.status)
    return update_mailbox_status(
        session,
        mailbox_id=mailbox_id,
        status=status_val,
        actor=actor,
        peer=request.client.host if request.client else None,
    )


@router.post("/{mailbox_id}/verify-gmail", response_model=GmailVerificationResponse)
def verify_gmail(
    mailbox_id: UUID, body: GmailVerificationRequest, session: Database, actor: CurrentUser
):
    mailbox = get_mailbox(session, mailbox_id)
    if mailbox is None or mailbox.user_id != actor.id:
        raise HTTPException(404, "Mailbox not found")
    if mailbox.provider != "gmail":
        raise HTTPException(400, "Gmail mailbox required")
    try:
        verify_gmail_access(mailbox.email_address, body.app_password.get_secret_value())
    except GmailAuthenticationFailed:
        raise HTTPException(400, "Gmail authentication failed") from None
    except GmailUnavailable:
        raise HTTPException(503, "Gmail connection unavailable") from None
    return {"verified": True}
