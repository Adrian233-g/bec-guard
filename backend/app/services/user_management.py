"""Administrative user management with audit and serialized access changes."""

from ipaddress import ip_address
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.passwords import hash_password, verify_password
from app.models import AuditLog, Role, User
from app.schemas.users import UserCreate, UserUpdate
from app.services.audit import AuditAction


def _audit(session: Session, *, actor: User, target: User, action: AuditAction, peer: str | None):
    try:
        address = str(ip_address(peer)) if peer else None
    except ValueError:
        address = None
    session.add(
        AuditLog(
            actor_user_id=actor.id,
            actor_role=actor.role,
            action=action.value,
            resource_type="user",
            resource_id=target.id,
            ip_address=address,
        )
    )


def _locked_admin(session: Session, actor: User) -> User:
    # Serialize role changes and re-check the actor after acquiring the lock.
    session.execute(text("LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE"))
    session.refresh(actor)
    if not actor.is_active or actor.role != Role.ADMIN:
        raise HTTPException(403, "Forbidden")
    return actor


def create_user(session: Session, body: UserCreate, *, actor: User, peer: str | None) -> User:
    password_hash = hash_password(body.password.get_secret_value())
    _locked_admin(session, actor)
    user = User(name=body.name, email=str(body.email), role=body.role, password_hash=password_hash)
    try:
        session.add(user)
        session.flush()
        _audit(session, actor=actor, target=user, action=AuditAction.USER_CREATED, peer=peer)
        session.commit()
        session.refresh(user)
        return user
    except SQLAlchemyError as error:
        session.rollback()
        if (
            isinstance(error, IntegrityError)
            and getattr(error.orig, "sqlstate", None) == "23505"
            and getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == "uq_users_email_lower"
        ):
            raise HTTPException(409, "User email already exists") from None
        raise


def update_user(
    session: Session, user_id: UUID, body: UserUpdate, *, actor: User, peer: str | None
) -> User:
    _locked_admin(session, actor)
    target = session.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True)
    changed = {name for name, value in changes.items() if getattr(target, name) != value}
    if not changed:
        return target
    if target.id == actor.id and (
        changes.get("is_active") is False or changes.get("role", Role.ADMIN) != Role.ADMIN
    ):
        raise HTTPException(409, "Cannot deactivate or demote your own account")
    for name in changed:
        setattr(target, name, changes[name])
    try:
        session.flush()
        _audit(session, actor=actor, target=target, action=AuditAction.USER_UPDATED, peer=peer)
        session.commit()
        session.refresh(target)
        return target
    except SQLAlchemyError:
        session.rollback()
        raise


def change_password(
    session: Session, actor: User, current: str, new: str, *, peer: str | None
) -> None:
    # Row lock serializes password changes and makes a stale current password fail.
    target = session.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target is None or not target.is_active or not verify_password(current, target.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if verify_password(new, target.password_hash):
        raise HTTPException(400, "New password must differ")
    target.password_hash = hash_password(new)
    try:
        _audit(
            session,
            actor=target,
            target=target,
            action=AuditAction.USER_PASSWORD_CHANGED,
            peer=peer,
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
