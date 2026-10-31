"""Introduce EMPLOYEE while preserving historical audit role snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0009_roles_employee"
down_revision = "0008_alert_hitl_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE public.users IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM public.users WHERE role IN ('MANAGER', 'AUDITOR'))"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Reassign MANAGER/AUDITOR users explicitly before migrating roles")
    op.drop_constraint(op.f("ck_users_role"), "users", schema="public")
    op.alter_column(
        "users", "role", type_=sa.String(8), existing_type=sa.String(7), schema="public"
    )
    op.create_check_constraint(
        op.f("ck_users_role"), "users", "role IN ('ADMIN', 'ANALYST', 'EMPLOYEE')", schema="public"
    )
    op.drop_constraint(op.f("ck_audit_log_actor_role"), "audit_log", schema="public")
    op.alter_column(
        "audit_log", "actor_role", type_=sa.String(8), existing_type=sa.String(7), schema="public"
    )
    op.create_check_constraint(
        op.f("ck_audit_log_actor_role"),
        "audit_log",
        "actor_role IN ('ADMIN', 'ANALYST', 'EMPLOYEE', 'MANAGER', 'AUDITOR')",
        schema="public",
    )


def downgrade():
    op.execute("LOCK TABLE public.users IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.audit_log IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM public.users WHERE role = 'EMPLOYEE') OR "
                "EXISTS (SELECT 1 FROM public.audit_log WHERE actor_role = 'EMPLOYEE')"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while EMPLOYEE users or audit snapshots exist")
    op.drop_constraint(op.f("ck_audit_log_actor_role"), "audit_log", schema="public")
    op.alter_column(
        "audit_log", "actor_role", type_=sa.String(7), existing_type=sa.String(8), schema="public"
    )
    op.create_check_constraint(
        op.f("ck_audit_log_actor_role"),
        "audit_log",
        "actor_role IN ('ADMIN', 'ANALYST', 'MANAGER', 'AUDITOR')",
        schema="public",
    )
    op.drop_constraint(op.f("ck_users_role"), "users", schema="public")
    op.alter_column(
        "users", "role", type_=sa.String(7), existing_type=sa.String(8), schema="public"
    )
    op.create_check_constraint(
        op.f("ck_users_role"),
        "users",
        "role IN ('ADMIN', 'ANALYST', 'MANAGER', 'AUDITOR')",
        schema="public",
    )
