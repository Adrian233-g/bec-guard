"""Create mailboxes table and associate emails with mailboxes.

Revision ID: 0010_mailboxes_and_ownership
Revises: 0009_roles_employee
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0010_mailboxes_and_ownership"
down_revision = "0009_roles_employee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create mailboxes table
    op.create_table(
        "mailboxes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("provider", sa.String(32), server_default="gmail", nullable=False),
        sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailboxes")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            name=op.f("fk_mailboxes_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISCONNECTED', 'ERROR')", name=op.f("ck_mailboxes_status")
        ),
        sa.CheckConstraint(
            "provider IN ('gmail', 'imap', 'other')", name=op.f("ck_mailboxes_provider")
        ),
        schema="public",
    )
    op.create_index(
        "uq_mailboxes_email_lower",
        "mailboxes",
        [sa.text("lower(email_address)")],
        unique=True,
        schema="public",
    )
    op.create_index(
        "uq_mailboxes_user_id",
        "mailboxes",
        ["user_id"],
        unique=True,
        schema="public",
    )

    # 2. Add nullable mailbox_id column to emails
    op.add_column("emails", sa.Column("mailbox_id", sa.Uuid(), nullable=True), schema="public")

    # 3. Handle data migration if emails already exist
    bind = op.get_bind()
    has_emails = bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM public.emails)")).scalar()
    if has_emails:
        user_row = bind.execute(
            sa.text(
                "SELECT id, email FROM public.users "
                "ORDER BY "
                "  CASE WHEN role = 'EMPLOYEE' THEN 1 WHEN role = 'ADMIN' THEN 2 ELSE 3 END, "
                "  created_at "
                "LIMIT 1"
            )
        ).first()
        if not user_row:
            raise RuntimeError(
                "Cannot migrate existing emails without an existing user. "
                "Create an employee or admin first."
            )
        user_id, user_email = user_row
        mailbox_id = uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO public.mailboxes (id, user_id, email_address, provider, status) "
                "VALUES (:id, :user_id, :email, 'gmail', 'ACTIVE')"
            ),
            {"id": mailbox_id, "user_id": user_id, "email": user_email},
        )
        bind.execute(
            sa.text("UPDATE public.emails SET mailbox_id = :mailbox_id WHERE mailbox_id IS NULL"),
            {"mailbox_id": mailbox_id},
        )

    # 4. Alter mailbox_id to NOT NULL
    op.alter_column("emails", "mailbox_id", nullable=False, schema="public")

    # 5. Add foreign key from emails.mailbox_id to mailboxes.id
    op.create_foreign_key(
        op.f("fk_emails_mailbox_id_mailboxes"),
        "emails",
        "mailboxes",
        ["mailbox_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )

    # 6. Update uniqueness and indexes on emails
    op.drop_constraint("uq_emails_message_id", "emails", schema="public")
    op.create_unique_constraint(
        op.f("uq_emails_mailbox_message_id"),
        "emails",
        ["mailbox_id", "message_id"],
        schema="public",
    )
    op.create_index(
        "ix_emails_mailbox_received_at_id",
        "emails",
        ["mailbox_id", sa.text("received_at DESC"), "id"],
        schema="public",
    )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT message_id FROM public.emails GROUP BY message_id HAVING COUNT(*) > 1"
            ") s"
        )
    ).scalar()
    if duplicate_count and duplicate_count > 0:
        raise RuntimeError("Cannot downgrade: duplicate message_id exists across mailboxes.")

    op.drop_index("ix_emails_mailbox_received_at_id", table_name="emails", schema="public")
    op.drop_constraint(op.f("uq_emails_mailbox_message_id"), "emails", schema="public")

    op.create_unique_constraint(
        op.f("uq_emails_message_id"),
        "emails",
        ["message_id"],
        schema="public",
    )

    op.drop_constraint(op.f("fk_emails_mailbox_id_mailboxes"), "emails", schema="public")
    op.drop_column("emails", "mailbox_id", schema="public")

    op.drop_index("uq_mailboxes_user_id", table_name="mailboxes", schema="public")
    op.drop_index("uq_mailboxes_email_lower", table_name="mailboxes", schema="public")
    op.drop_table("mailboxes", schema="public")
