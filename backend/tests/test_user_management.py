from uuid import UUID

import pytest
from sqlalchemy import select, text

from app.core.passwords import verify_password
from app.core.tokens import create_access_token
from app.models import AuditLog, Role, User

pytestmark = pytest.mark.integration
INITIAL = "initial password 123"
NEW = "changed password 456"


@pytest.fixture
def admin(account, db_session, auth_settings):
    account.role = Role.ADMIN
    db_session.commit()
    return account, {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}


def test_admin_create_and_manage_users_without_exposing_password(api_client, db_session, admin):
    actor, headers = admin
    body = {"name": " Ana ", "email": " ANA@Example.com ", "role": "EMPLOYEE", "password": INITIAL}
    response = api_client.post("/api/users", json=body, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Ana" and data["email"] == "ana@example.com"
    assert data["role"] == "EMPLOYEE" and data["is_active"] is True
    assert "password" not in response.text and INITIAL not in response.text
    user = db_session.get(User, UUID(data["id"]))
    assert verify_password(INITIAL, user.password_hash)
    assert api_client.post("/api/users", json=body, headers=headers).status_code == 409
    listed = api_client.get("/api/users?limit=1&offset=1", headers=headers)
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert (
        api_client.patch(
            f"/api/users/{user.id}", json={"role": "ANALYST", "is_active": False}, headers=headers
        ).status_code
        == 200
    )
    db_session.refresh(user)
    assert user.role == Role.ANALYST and not user.is_active
    assert (
        api_client.patch(f"/api/users/{user.id}", json={"is_active": True}, headers=headers).json()[
            "is_active"
        ]
        is True
    )
    events = list(
        db_session.scalars(
            select(AuditLog).where(AuditLog.action.in_(["USER_CREATED", "USER_UPDATED"]))
        )
    )
    assert [e.action for e in events].count("USER_CREATED") == 1
    assert len(events) == 3 and all(
        e.actor_user_id == actor.id and e.resource_id == user.id for e in events
    )
    assert all(e.details is None for e in events)
    assert INITIAL not in str([(e.action, e.details) for e in events])


@pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.ANALYST])
def test_non_admin_cannot_manage_users(api_client, account, db_session, auth_settings, role):
    account.role = role
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    assert api_client.get("/api/users", headers=headers).status_code == 403
    assert (
        api_client.post(
            "/api/users",
            json={"name": "X", "email": "x@example.com", "role": "EMPLOYEE", "password": INITIAL},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        api_client.patch(
            f"/api/users/{account.id}", json={"role": "ADMIN"}, headers=headers
        ).status_code
        == 403
    )


def test_admin_cannot_deactivate_or_demote_self(api_client, admin):
    actor, headers = admin
    for payload in [
        {"is_active": False},
        {"role": "EMPLOYEE"},
        {"role": "ANALYST", "is_active": False},
    ]:
        assert (
            api_client.patch(f"/api/users/{actor.id}", json=payload, headers=headers).status_code
            == 409
        )
    assert api_client.get("/api/auth/me", headers=headers).json()["role"] == "ADMIN"
    assert (
        api_client.patch(f"/api/users/{actor.id}", json={"role": None}, headers=headers).status_code
        == 400
    )


def test_password_change_verifies_current_and_supports_login(
    api_client, account, db_session, auth_settings
):
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    old = "a long test password"
    assert (
        api_client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": "incorrect", "new_password": NEW},
        ).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": old, "new_password": old},
        ).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": old, "new_password": NEW},
        ).status_code
        == 204
    )
    assert (
        api_client.post(
            "/api/auth/login", json={"email": account.email, "password": old}
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/auth/login", json={"email": account.email, "password": NEW}
        ).status_code
        == 200
    )
    event = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "USER_PASSWORD_CHANGED")
    ).one()
    assert event.actor_user_id == account.id and event.details is None


def test_create_rollback_if_audit_fails(api_client, migrated_engine, db_session, admin):
    _, headers = admin
    with migrated_engine.begin() as c:
        c.execute(
            text(
                "CREATE FUNCTION public.reject_test_user_audit() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.action = 'USER_CREATED' THEN "
                "RAISE EXCEPTION 'audit failure' USING ERRCODE = '23514'; "
                "END IF; RETURN NEW; END; $$"
            )
        )
        c.execute(
            text(
                "CREATE TRIGGER reject_test_user_audit BEFORE INSERT ON public.audit_log "
                "FOR EACH ROW EXECUTE FUNCTION public.reject_test_user_audit()"
            )
        )
    try:
        result = api_client.post(
            "/api/users",
            json={
                "name": "Ana",
                "email": "new@example.com",
                "role": "EMPLOYEE",
                "password": INITIAL,
            },
            headers=headers,
        )
        assert result.status_code == 503
        assert db_session.scalar(select(User).where(User.email == "new@example.com")) is None
    finally:
        db_session.rollback()
        with migrated_engine.begin() as c:
            c.execute(text("DROP TRIGGER reject_test_user_audit ON public.audit_log"))
            c.execute(text("DROP FUNCTION public.reject_test_user_audit()"))


def test_simultaneous_admin_demotions_cannot_leave_zero_admins(migrated_engine, db_session, admin):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi import HTTPException
    from sqlalchemy.orm import Session

    from app.schemas.users import UserUpdate
    from app.services.user_management import update_user

    first, _ = admin
    second = User(
        name="Second",
        email="second@example.com",
        role=Role.ADMIN,
        password_hash=first.password_hash,
    )
    db_session.add(second)
    db_session.commit()
    first_id, second_id = first.id, second.id
    gate = Barrier(2)

    def demote(actor_id, target_id):
        with Session(migrated_engine) as session:
            actor = session.get(User, actor_id)
            gate.wait(timeout=10)
            try:
                update_user(
                    session, target_id, UserUpdate(role=Role.EMPLOYEE), actor=actor, peer=None
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(demote, first_id, second_id), pool.submit(demote, second_id, first_id)]
        assert sorted(job.result(timeout=20) for job in jobs) == [200, 403]
    db_session.expire_all()
    assert (
        sum(user.role == Role.ADMIN and user.is_active for user in db_session.scalars(select(User)))
        == 1
    )
