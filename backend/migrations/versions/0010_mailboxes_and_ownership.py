"""Create mailboxes table and associate emails with mailboxes.

Revision ID: 0010_mailboxes_and_ownership
Revises: 0009_roles_employee
"""

from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import context, op
from email_validator import EmailNotValidError, validate_email

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
        args = context.get_x_argument(as_dictionary=True)
        try:
            user_id = UUID(args.get("legacy_owner_id", ""))
            user_email = validate_email(
                args.get("legacy_mailbox_address", ""), check_deliverability=False
            ).normalized.lower()
        except ValueError, EmailNotValidError:
            raise RuntimeError(
                "Existing emails require explicit -x legacy_owner_id and "
                "-x legacy_mailbox_address; ownership must be confirmed by the operator"
            ) from None
        user_row = bind.execute(
            sa.text("SELECT id FROM public.users WHERE id = :id AND is_active = true"),
            {"id": user_id},
        ).first()
        if not user_row:
            raise RuntimeError("Explicit legacy owner must be an existing active user")
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
