from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select

from app.api.dependencies import get_automation_settings, require_automation_key
from app.api.email_analysis import get_analyzer_factory
from app.api.emails import Database
from app.core.config import AutomationSettings
from app.models import BECAlert, Email, Mailbox, User
from app.models.enums import AnalysisStatus
from app.schemas.automation import AutomationAnalysisResponse, AutomationIngestResponse
from app.schemas.email import EmailIngestRequest
from app.services.email_analysis import analyze_email
from app.services.email_ingestion import ingest_email_idempotently
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalyzer

router = APIRouter(
    prefix="/api/automation/emails",
    tags=["n8n automation"],
    dependencies=[Depends(require_automation_key)],
)
Settings = Annotated[AutomationSettings, Depends(get_automation_settings)]


def _trusted_mailbox(session: Database, settings: AutomationSettings) -> Mailbox:
    # This key is scoped server-side to ONE explicitly configured mailbox. The
    # email headers, payload and query parameters never choose its owner.
    try:
        mailbox_id = UUID(settings.automation_mailbox_id.strip())
    except ValueError, AttributeError:
        raise HTTPException(503, "Automation mailbox not configured") from None
    mailbox = session.get(Mailbox, mailbox_id)
    owner = session.get(User, mailbox.user_id) if mailbox else None
    if not mailbox or mailbox.status != "ACTIVE" or not owner or not owner.is_active:
        raise HTTPException(503, "Automation mailbox unavailable")
    return mailbox


@router.post(
    "",
    response_model=AutomationIngestResponse,
    responses={201: {"model": AutomationIngestResponse}},
)
def ingest(
    body: EmailIngestRequest,
    session: Database,
    request: Request,
    response: Response,
    settings: Settings,
    mailbox_id: Annotated[UUID | None, Query()] = None,
):
    if mailbox_id is not None or body.mailbox_id is not None:
        raise HTTPException(400, "Mailbox is determined by the connector configuration")
    mailbox = _trusted_mailbox(session, settings)
    email, created = ingest_email_idempotently(
        session,
        body,
        mailbox_id=mailbox.id,
        peer=request.client.host if request.client else None,
    )
    response.status_code = 201 if created else 200
    return {"created": created, "email": email}


@router.post(
    "/{email_id}/analyze",
    response_model=AutomationAnalysisResponse,
    responses={
        502: {"model": AutomationAnalysisResponse},
        503: {"model": AutomationAnalysisResponse},
    },
)
def analyze(
    email_id: UUID,
    session: Database,
    request: Request,
    response: Response,
    settings: Settings,
    analyzer_factory: Annotated[Callable[[], SemanticAnalyzer], Depends(get_analyzer_factory)],
):
    mailbox = _trusted_mailbox(session, settings)
    email = session.get(Email, email_id)
    if email is None or email.mailbox_id != mailbox.id:
        raise HTTPException(404, "Email not found")
    analysis = analyze_email(
        session,
        email_id,
        actor=None,
        analyzer_factory=analyzer_factory,
        peer=request.client.host if request.client else None,
    )
    alert_id = None
    if analysis.status == AnalysisStatus.ERROR:
        response.status_code = 503 if analysis.error_code == LLMErrorCode.NOT_CONFIGURED else 502
    else:
        alert_id = session.scalar(select(BECAlert.id).where(BECAlert.analysis_id == analysis.id))
    return {"analysis": analysis, "alert_id": alert_id}
