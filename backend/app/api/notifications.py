from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_roles
from app.api.emails import Database
from app.models import Role, User
from app.schemas.notifications import NotificationResponse, ReadAllResponse, UnreadCountResponse
from app.services import notifications as notification_service

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
Reader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST, Role.EMPLOYEE))]


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    session: Database,
    actor: Reader,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread_only: bool = False,
):
    return notification_service.list_notifications(
        session,
        user_id=actor.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(session: Database, actor: Reader):
    return {"count": notification_service.unread_count(session, user_id=actor.id)}


@router.post("/read-all", response_model=ReadAllResponse)
def mark_all_read(session: Database, actor: Reader):
    return {"updated": notification_service.mark_all_read(session, user_id=actor.id)}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: UUID, session: Database, actor: Reader) -> None:
    if not notification_service.mark_read(
        session, user_id=actor.id, notification_id=notification_id
    ):
        raise HTTPException(404, "Notification not found")
