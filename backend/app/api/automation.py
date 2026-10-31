from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from app.api.dependencies import require_automation_key
from app.api.email_analysis import get_analyzer_factory
from app.api.emails import Database
from app.models import BECAlert, Mailbox
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
    mailbox_id: Annotated[UUID | None, Query()] = None,
):
    target_mailbox_id = mailbox_id or body.mailbox_id
    if target_mailbox_id is not None:
        mailbox = session.get(Mailbox, target_mailbox_id)
        if mailbox is None or mailbox.status != "ACTIVE":
            raise HTTPException(404, "Mailbox not found or inactive")
        target_mailbox_id = mailbox.id
    else:
        if body.to_recipients:
            normalized_to = [r.strip().lower() for r in body.to_recipients]
            target_mailbox_id = session.scalar(
                select(Mailbox.id).where(
                    func.lower(Mailbox.email_address).in_(normalized_to),
                    Mailbox.status == "ACTIVE",
                )
            )
        if target_mailbox_id is None:
            active_mailboxes = list(
                session.scalars(select(Mailbox.id).where(Mailbox.status == "ACTIVE").limit(2))
            )
            if len(active_mailboxes) == 1:
                target_mailbox_id = active_mailboxes[0]

        if target_mailbox_id is None:
            raise HTTPException(422, "No active mailbox matches recipient")

    email, created = ingest_email_idempotently(
        session,
        body,
        mailbox_id=target_mailbox_id,
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
    analyzer_factory: Annotated[Callable[[], SemanticAnalyzer], Depends(get_analyzer_factory)],
):
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
