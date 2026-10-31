from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import exists, select

from app.api.dependencies import require_roles
from app.api.emails import Database
from app.models import BECAlert, Email, EmailAnalysis, Mailbox, Role, User
from app.models.enums import AnalysisStatus
from app.schemas.analysis import EmailAnalysisResponse
from app.services.email_analysis import analyze_email, create_semantic_analyzer
from app.services.semantic_analysis import LLMErrorCode, SemanticAnalyzer

router = APIRouter(prefix="/api/emails", tags=["BEC analysis"])
AnyUser = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST, Role.EMPLOYEE))]


def get_analyzer_factory() -> Callable[[], SemanticAnalyzer]:
    # Return a factory: invalid/missing settings become a persisted ERROR, and a
    # completed analysis or missing email never needs provider configuration.
    return create_semantic_analyzer


def _check_email_access(session: Database, email_id: UUID, actor: User) -> Email:
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


@router.post(
    "/{email_id}/analyze",
    response_model=EmailAnalysisResponse,
    responses={502: {"model": EmailAnalysisResponse}, 503: {"model": EmailAnalysisResponse}},
)
def post_analysis(
    email_id: UUID,
    session: Database,
    actor: AnyUser,
    request: Request,
    response: Response,
    analyzer_factory: Annotated[Callable[[], SemanticAnalyzer], Depends(get_analyzer_factory)],
):
    _check_email_access(session, email_id, actor)
    analysis = analyze_email(
        session,
        email_id,
        actor=actor,
        analyzer_factory=analyzer_factory,
        peer=request.client.host if request.client else None,
    )
    if analysis.status == AnalysisStatus.ERROR:
        response.status_code = 503 if analysis.error_code == LLMErrorCode.NOT_CONFIGURED else 502
    return analysis


@router.get("/{email_id}/analysis", response_model=EmailAnalysisResponse)
def get_analysis(email_id: UUID, session: Database, actor: AnyUser):
    _check_email_access(session, email_id, actor)
    analysis = session.scalar(select(EmailAnalysis).where(EmailAnalysis.email_id == email_id))
    if analysis is None:
        raise HTTPException(404, "Email analysis not found")
    return analysis
