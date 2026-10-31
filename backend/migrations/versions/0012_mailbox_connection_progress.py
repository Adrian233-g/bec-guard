"""Record non-secret mailbox provisioning progress for recovery."""

import sqlalchemy as sa
from alembic import op

revision = "0012_mailbox_connection_progress"
down_revision = "0011_mailbox_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailbox_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mailbox_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("imap_credential_id", sa.String(16), nullable=False),
        sa.Column("automation_credential_id", sa.String(16), nullable=False),
        sa.Column("workflow_id", sa.String(128), nullable=True),
        sa.Column("needs_reconciliation", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_connections")),
        sa.ForeignKeyConstraint(
            ["mailbox_id"],
            ["public.mailboxes.id"],
            name=op.f("fk_mailbox_connections_mailbox_id_mailboxes"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "stage IN ('allocated', 'imap-created', 'imap-verified', 'automation-created', "
            "'workflow-created', 'active', 'workflow-unpublished', 'workflow-deleted', "
            "'imap-deleted', 'automation-deleted')",
            name=op.f("ck_mailbox_connections_stage"),
        ),
        schema="public",
    )
    op.create_index(
        "uq_mailbox_connections_mailbox_id",
        "mailbox_connections",
        ["mailbox_id"],
        unique=True,
        schema="public",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM public.mailbox_connections)")).scalar():
        raise RuntimeError("Cannot downgrade while mailbox connection records exist")
    op.drop_index(
        "uq_mailbox_connections_mailbox_id", table_name="mailbox_connections", schema="public"
    )
    op.drop_table("mailbox_connections", schema="public")
