from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import DateTime, inspect, text

pytestmark = pytest.mark.integration


def test_upgrade_downgrade_upgrade_and_metadata_match(migrated_engine, migration_runner):
    def tables():
        return set(inspect(migrated_engine).get_table_names(schema="public"))

    # The session fixture already applied upgrade head to the clean test database.
    assert tables() == {
        "users",
        "audit_log",
        "executive_contacts",
        "vendors",
        "mailboxes",
        "mailbox_connections",
        "emails",
        "email_analysis",
        "bec_alerts",
        "notifications",
        "alembic_version",
    }
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            "0016_context_responsibilities"
        )

    migration_runner(command.downgrade, "0007_bec_alerts")
    migration_runner(command.upgrade, "head")
    migration_runner(command.check)

    migration_runner(command.downgrade, "0006_email_analysis")
    assert "bec_alerts" not in tables() and "email_analysis" in tables()
    migration_runner(command.upgrade, "head")
    migration_runner(command.check)

    migration_runner(command.downgrade, "0005_email_ingestion")
    assert "email_analysis" not in tables() and "emails" in tables()
    migration_runner(command.upgrade, "head")
    migration_runner(command.check)

    migration_runner(command.downgrade, "0004_organizational_context")
    assert tables() == {"users", "audit_log", "executive_contacts", "vendors", "alembic_version"}
    migration_runner(command.upgrade, "head")
    migration_runner(command.check)
    migration_runner(command.downgrade, "0003_create_audit_log")
    assert tables() == {"users", "audit_log", "alembic_version"}
    migration_runner(command.upgrade, "head")
    migration_runner(command.check)
    migration_runner(command.downgrade, "0001_create_users")
    assert tables() == {"users", "alembic_version"}
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regprocedure('public.reject_audit_log_mutation()')"))
            is None
        )
    migration_runner(command.upgrade, "head")
    migration_runner(command.downgrade, "base")
    assert tables() == {"alembic_version"}
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.alembic_version")) == 0

    migration_runner(command.upgrade, "head")
    assert tables() == {
        "users",
        "audit_log",
        "executive_contacts",
        "vendors",
        "mailboxes",
        "mailbox_connections",
        "emails",
        "email_analysis",
        "bec_alerts",
        "notifications",
        "alembic_version",
    }
    inspector = inspect(migrated_engine)
    columns = inspector.get_columns("users", schema="public")
    assert {column["name"] for column in columns} == {
        "id",
        "name",
        "email",
        "password_hash",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert all(column["nullable"] is False for column in columns)
    for column in columns:
        if column["name"] in {"created_at", "updated_at"}:
            assert isinstance(column["type"], DateTime)
            assert column["type"].timezone is True
    indexes = inspector.get_indexes("users", schema="public")
    assert len(indexes) == 1  # Only the functional UNIQUE index; no redundant email index.
    assert indexes[0]["name"] == "uq_users_email_lower"
    assert indexes[0]["unique"] is True
    assert indexes[0]["expressions"] == ["lower(email::text)"]
    for table, field, index_name in [
        ("executive_contacts", "email", "uq_executive_contacts_email_lower"),
        ("vendors", "domain", "uq_vendors_domain_lower"),
    ]:
        context_indexes = inspector.get_indexes(table, schema="public")
        assert len(context_indexes) == 1
        assert context_indexes[0]["name"] == index_name
        assert context_indexes[0]["unique"] is True
        assert context_indexes[0]["expressions"] == [f"lower({field}::text)"]
        for column in inspector.get_columns(table, schema="public"):
            if column["name"] in {"created_at", "updated_at"}:
                assert column["type"].timezone is True
                assert column["nullable"] is False
    email_columns = inspector.get_columns("emails", schema="public")
    assert {column["name"] for column in email_columns} == {
        "id",
        "mailbox_id",
        "message_id",
        "thread_id",
        "sender_name",
        "sender_email",
        "reply_to",
        "return_path",
        "to_recipients",
        "cc_recipients",
        "subject",
        "body_text",
        "authentication_results",
        "received_at",
        "ingested_at",
    }
    for column in email_columns:
        if column["name"] in {"received_at", "ingested_at"}:
            assert column["type"].timezone is True
            assert column["nullable"] is False
    assert inspector.get_unique_constraints("emails", schema="public") == [
        {
            "column_names": ["mailbox_id", "message_id"],
            "name": "uq_emails_mailbox_message_id",
            "comment": None,
            "dialect_options": {"postgresql_include": [], "postgresql_nulls_not_distinct": False},
        }
    ]
    migration_runner(command.check)


def test_identity_migration_rejects_collisions_without_merging(migrated_engine, migration_runner):
    migration_runner(command.downgrade, "0001_create_users")
    try:
        with migrated_engine.begin() as connection:
            for email in ["admin@example.com", " ADMIN@EXAMPLE.COM "]:
                connection.execute(
                    text(
                        "INSERT INTO public.users (id, name, email, password_hash, role) "
                        "VALUES (:id, 'Collision fixture', :email, 'opaque-test-marker', 'ADMIN')"
                    ),
                    {"id": uuid4(), "email": email},
                )
        with pytest.raises(RuntimeError, match="normalization collision"):
            migration_runner(command.upgrade, "head")
        with migrated_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM public.users")) == 2
            assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
                "0001_create_users"
            )
    finally:
        with migrated_engine.begin() as connection:
            connection.execute(text("DELETE FROM public.users"))
        migration_runner(command.upgrade, "head")


def test_role_migration_requires_explicit_reassignment_preserves_audit(
    migrated_engine, migration_runner, db_session
):
    from app.models import AuditLog
    from app.models.enums import AuditRole

    migration_runner(command.downgrade, "0008_alert_hitl_constraints")
    user_id, event_id = uuid4(), uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'Legacy', 'legacy@example.com', 'hash', 'MANAGER')"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.audit_log (id, actor_user_id, actor_role, action) "
                "VALUES (:id, :user_id, 'MANAGER', 'LEGACY_EVENT')"
            ),
            {"id": event_id, "user_id": user_id},
        )
    with pytest.raises(RuntimeError, match="Reassign MANAGER/AUDITOR"):
        migration_runner(command.upgrade, "head")
    with migrated_engine.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            "0008_alert_hitl_constraints"
        )
        connection.execute(
            text("UPDATE public.users SET role='ADMIN' WHERE id=:id"), {"id": user_id}
        )
    migration_runner(command.upgrade, "head")
    event = db_session.get(AuditLog, event_id)
    assert event.actor_role is AuditRole.MANAGER
    migration_runner(command.check)


def test_role_migration_refuses_downgrade_with_employee_history(
    migrated_engine, migration_runner, db_session
):
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.audit_log (id, actor_role, action) "
                "VALUES (:id, 'EMPLOYEE', 'EXAMPLE')"
            ),
            {"id": uuid4()},
        )
    with pytest.raises(RuntimeError, match="EMPLOYEE users or audit snapshots"):
        migration_runner(command.downgrade, "0008_alert_hitl_constraints")
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            "0016_context_responsibilities"
        )


def test_rate_limit_code_refuses_downgrade_before_0013(
    migrated_engine, migration_runner, db_session
):
    user_id, mailbox_id, email_id, analysis_id = uuid4(), uuid4(), uuid4(), uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'Rate', 'rate-0014@example.com', 'hash', 'EMPLOYEE')"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.mailboxes (id, user_id, email_address, status) "
                "VALUES (:id, :owner, 'rate-0014@gmail.com', 'ACTIVE')"
            ),
            {"id": mailbox_id, "owner": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.emails (id, mailbox_id, message_id, sender_email, subject, "
                "body_text, to_recipients, cc_recipients, received_at) "
                "VALUES (:id, :mb, '<rate-0014@example.com>', 's@example.com', "
                "'subject', 'body', '[]', '[]', NOW())"
            ),
            {"id": email_id, "mb": mailbox_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.email_analysis (id, email_id, status, deterministic_score, "
                "signals, policy_version, error_code, analyzed_at) "
                "VALUES (:id, :email, 'ERROR', 0, '[]', 'det-v1', 'LLM_RATE_LIMITED', NOW())"
            ),
            {"id": analysis_id, "email": email_id},
        )
    with pytest.raises(RuntimeError, match="LLM_RATE_LIMITED"):
        migration_runner(command.downgrade, "0013_notifications")
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            "0016_context_responsibilities"
        )


def test_mailbox_migration_refuses_downgrade_with_duplicate_message_ids(
    migrated_engine, migration_runner, db_session
):
    with migrated_engine.begin() as connection:
        user1 = uuid4()
        user2 = uuid4()
        mb1 = uuid4()
        mb2 = uuid4()
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'U1', 'u1@example.com', 'hash', 'EMPLOYEE')"
            ),
            {"id": user1},
        )
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'U2', 'u2@example.com', 'hash', 'EMPLOYEE')"
            ),
            {"id": user2},
        )
        connection.execute(
            text(
                "INSERT INTO public.mailboxes (id, user_id, email_address, provider, status) "
                "VALUES (:id, :u, 'u1@example.com', 'gmail', 'ACTIVE')"
            ),
            {"id": mb1, "u": user1},
        )
        connection.execute(
            text(
                "INSERT INTO public.mailboxes (id, user_id, email_address, provider, status) "
                "VALUES (:id, :u, 'u2@example.com', 'gmail', 'ACTIVE')"
            ),
            {"id": mb2, "u": user2},
        )
        connection.execute(
            text(
                "INSERT INTO public.emails ("
                "  id, mailbox_id, message_id, sender_email, subject, body_text, "
                "  to_recipients, cc_recipients, received_at"
                ") VALUES ("
                "  :id, :mb, '<dup@example.com>', 's@example.com', 'sub', 'body', "
                "  '[]', '[]', NOW()"
                ")"
            ),
            {"id": uuid4(), "mb": mb1},
        )
        connection.execute(
            text(
                "INSERT INTO public.emails ("
                "  id, mailbox_id, message_id, sender_email, subject, body_text, "
                "  to_recipients, cc_recipients, received_at"
                ") VALUES ("
                "  :id, :mb, '<dup@example.com>', 's@example.com', 'sub', 'body', "
                "  '[]', '[]', NOW()"
                ")"
            ),
            {"id": uuid4(), "mb": mb2},
        )
    with pytest.raises(RuntimeError, match="duplicate message_id exists across mailboxes"):
        migration_runner(command.downgrade, "0009_roles_employee")


def test_legacy_emails_require_explicit_confirmed_owner(
    migrated_engine, migration_runner, db_session
):
    migration_runner(command.downgrade, "0009_roles_employee")
    owner_id, email_id = uuid4(), uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'Owner', 'login@example.com', 'hash', 'EMPLOYEE')"
            ),
            {"id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.emails (id, message_id, sender_email, subject, body_text, "
                "to_recipients, cc_recipients, received_at) VALUES (:id, '<legacy@example.com>', "
                "'s@example.com', 'subject', 'body', '[]', '[]', NOW())"
            ),
            {"id": email_id},
        )
    with pytest.raises(RuntimeError, match="require explicit"):
        migration_runner(command.upgrade, "head")
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "0009_roles_employee"
        )
        assert connection.scalar(text("SELECT count(*) FROM public.emails")) == 1
    migration_runner(
        command.upgrade,
        "head",
        x_args=[f"legacy_owner_id={owner_id}", "legacy_mailbox_address=actual@gmail.com"],
    )
    with migrated_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT m.user_id, m.email_address, m.status FROM public.emails e "
                "JOIN public.mailboxes m ON m.id=e.mailbox_id WHERE e.id=:id"
            ),
            {"id": email_id},
        ).one()
        assert row == (owner_id, "actual@gmail.com", "PENDING")


def test_existing_0010_ownership_must_be_reviewed_and_mailbox_quarantined(
    migrated_engine, migration_runner, db_session
):
    migration_runner(command.downgrade, "0010_mailboxes_and_ownership")
    owner_id, mailbox_id, email_id = uuid4(), uuid4(), uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'Owner', 'owner-0010@example.com', 'hash', 'EMPLOYEE')"
            ),
            {"id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.mailboxes (id, user_id, email_address, status) "
                "VALUES (:id, :owner, 'owner-0010@gmail.com', 'ACTIVE')"
            ),
            {"id": mailbox_id, "owner": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.emails (id, mailbox_id, message_id, sender_email, subject, "
                "body_text, to_recipients, cc_recipients, received_at) "
                "VALUES (:id, :mb, '<legacy-0010@example.com>', 's@example.com', "
                "'subject', 'body', '[]', '[]', NOW())"
            ),
            {"id": email_id, "mb": mailbox_id},
        )
    with pytest.raises(RuntimeError, match="ownership requires review"):
        migration_runner(command.upgrade, "head")
    migration_runner(command.upgrade, "head", x_args=["confirm_existing_ownership=true"])
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT status FROM public.mailboxes WHERE id=:id"), {"id": mailbox_id}
            )
            == "PENDING"
        )
        assert (
            connection.scalar(
                text("SELECT mailbox_id FROM public.emails WHERE id=:id"), {"id": email_id}
            )
            == mailbox_id
        )


def test_confirmed_legacy_connector_is_the_only_automatic_activation(
    migrated_engine, migration_runner, db_session
):
    migration_runner(command.downgrade, "0009_roles_employee")
    owner_id, email_id = uuid4(), uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, 'Owner', 'login-connector@example.com', 'hash', 'EMPLOYEE')"
            ),
            {"id": owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.emails (id, message_id, sender_email, subject, body_text, "
                "to_recipients, cc_recipients, received_at) "
                "VALUES (:id, '<connector@example.com>', "
                "'s@example.com', 'subject', 'body', '[]', '[]', NOW())"
            ),
            {"id": email_id},
        )
    migration_runner(
        command.upgrade,
        "head",
        x_args=[
            f"legacy_owner_id={owner_id}",
            "legacy_mailbox_address=connected@gmail.com",
            "legacy_connector_confirmed=true",
        ],
    )
    with migrated_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT m.user_id, m.email_address, m.status FROM public.emails e "
                "JOIN public.mailboxes m ON m.id=e.mailbox_id WHERE e.id=:id"
            ),
            {"id": email_id},
        ).one()
        assert row == (owner_id, "connected@gmail.com", "ACTIVE")
