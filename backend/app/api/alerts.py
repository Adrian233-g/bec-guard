from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.api.dependencies import require_roles
from app.api.emails import Database
from app.models import BECAlert, Email, EmailAnalysis, Mailbox, Role, User
from app.models.enums import AlertStatus, BECType, RiskLevel
from app.schemas.alerts import AlertDetailResponse, AlertResolveRequest, AlertSummaryResponse
from app.services.alerts import review_alert

router = APIRouter(prefix="/api/alerts", tags=["BEC alerts"])
Reader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST, Role.EMPLOYEE))]
Writer = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST))]


@router.get("", response_model=list[AlertSummaryResponse])
def list_alerts(
    session: Database,
    actor: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: AlertStatus | None = None,
    risk_level: RiskLevel | None = None,
    bec_type: BECType | None = None,
    assigned_to: UUID | None = None,
    analysis_id: UUID | None = None,
):
    # Select queue fields explicitly: never load the email body or provider output.
    OwnerUser = aliased(User)
    statement = (
        select(
            BECAlert.id,
            BECAlert.analysis_id,
            BECAlert.status,
            BECAlert.verdict,
            BECAlert.assigned_to,
            User.name.label("assigned_to_name"),
            Mailbox.id.label("mailbox_id"),
            Mailbox.email_address.label("mailbox_email"),
            OwnerUser.name.label("owner_name"),
            BECAlert.created_at,
            BECAlert.updated_at,
            Email.id.label("email_id"),
            EmailAnalysis.risk_score,
            EmailAnalysis.risk_level,
            EmailAnalysis.bec_type,
            Email.sender_name,
            Email.sender_email,
            Email.subject,
            Email.received_at,
        )
        .join(EmailAnalysis, BECAlert.analysis_id == EmailAnalysis.id)
        .join(Email, EmailAnalysis.email_id == Email.id)
        .join(Mailbox, Email.mailbox_id == Mailbox.id)
        .join(OwnerUser, Mailbox.user_id == OwnerUser.id)
        .outerjoin(User, BECAlert.assigned_to == User.id)
        .order_by(BECAlert.created_at.desc(), BECAlert.id)
        .limit(limit)
        .offset(offset)
    )
    if actor.role == Role.EMPLOYEE:
        statement = statement.where(Mailbox.user_id == actor.id)

    for column, value in [
        (BECAlert.status, status),
        (EmailAnalysis.risk_level, risk_level),
        (EmailAnalysis.bec_type, bec_type),
        (BECAlert.assigned_to, assigned_to),
        (BECAlert.analysis_id, analysis_id),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    return session.execute(statement).mappings().all()


@router.get("/{alert_id}", response_model=AlertDetailResponse)
def get_alert(alert_id: UUID, session: Database, actor: Reader):
    alert = session.get(BECAlert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")

    analysis = session.get(EmailAnalysis, alert.analysis_id)
    email = session.get(Email, analysis.email_id) if analysis else None
    mailbox = session.get(Mailbox, email.mailbox_id) if email else None
    owner = session.get(User, mailbox.user_id) if mailbox else None

    if actor.role == Role.EMPLOYEE:
        if not mailbox or mailbox.user_id != actor.id:
            raise HTTPException(404, "Alert not found")

    return {
        **{
            field: getattr(alert, field)
            for field in AlertDetailResponse.model_fields
            if field
            not in {
                "analysis",
                "assigned_to_name",
                "mailbox_id",
                "mailbox_email",
                "owner_name",
            }
        },
        "analysis": analysis,
        "assigned_to_name": (
            session.get(User, alert.assigned_to).name if alert.assigned_to else None
        ),
        "mailbox_id": mailbox.id if mailbox else None,
        "mailbox_email": mailbox.email_address if mailbox else None,
        "owner_name": owner.name if owner else None,
    }


@router.post("/{alert_id}/claim", response_model=AlertDetailResponse)
def claim_alert(alert_id: UUID, session: Database, actor: Writer, request: Request):
    review_alert(
        session,
        alert_id,
        operation="claim",
        actor=actor,
        peer=request.client.host if request.client else None,
    )
    return get_alert(alert_id, session, actor)


@router.post("/{alert_id}/release", response_model=AlertDetailResponse)
def release_alert(alert_id: UUID, session: Database, actor: Writer, request: Request):
    review_alert(
        session,
        alert_id,
        operation="release",
        actor=actor,
        peer=request.client.host if request.client else None,
    )
    return get_alert(alert_id, session, actor)


@router.post("/{alert_id}/resolve", response_model=AlertDetailResponse)
def resolve_alert(
    alert_id: UUID, body: AlertResolveRequest, session: Database, actor: Writer, request: Request
):
    review_alert(
        session,
        alert_id,
        operation="resolve",
        actor=actor,
        payload=body,
        peer=request.client.host if request.client else None,
    )
    return get_alert(alert_id, session, actor)
