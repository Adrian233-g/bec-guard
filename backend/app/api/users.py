from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_session
from app.models import Role, User
from app.schemas.auth import CurrentUserResponse
from app.schemas.users import PasswordChange, UserCreate, UserUpdate
from app.services.user_management import change_password, create_user, update_user

router = APIRouter(prefix="/api", tags=["Users"])
Database = Annotated[Session, Depends(get_session)]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Current = Annotated[User, Depends(get_current_user)]


@router.get("/users", response_model=list[CurrentUserResponse])
def list_users(
    session: Database,
    _actor: Admin,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list(
        session.scalars(select(User).order_by(User.created_at, User.id).limit(limit).offset(offset))
    )


@router.post("/users", response_model=CurrentUserResponse, status_code=201)
def post_user(body: UserCreate, session: Database, actor: Admin, request: Request):
    return create_user(
        session, body, actor=actor, peer=request.client.host if request.client else None
    )


@router.patch("/users/{user_id}", response_model=CurrentUserResponse)
def patch_user(user_id: UUID, body: UserUpdate, session: Database, actor: Admin, request: Request):
    return update_user(
        session, user_id, body, actor=actor, peer=request.client.host if request.client else None
    )


@router.post("/auth/change-password", status_code=204)
def post_change_password(body: PasswordChange, session: Database, actor: Current, request: Request):
    change_password(
        session,
        actor,
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
        peer=request.client.host if request.client else None,
    )
    return Response(status_code=204)
