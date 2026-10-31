"""Create in-app notifications for new BEC alerts."""

import sqlalchemy as sa
from alembic import op

revision = "0013_notifications"
down_revision = "0012_mailbox_connection_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), server_default="BEC_ALERT", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "user_id",
            "alert_id",
            "kind",
            name=op.f("uq_notifications_user_alert_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["public.bec_alerts.id"],
            name=op.f("fk_notifications_alert_id_bec_alerts"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("kind IN ('BEC_ALERT')", name=op.f("ck_notifications_kind")),
        schema="public",
    )
    op.create_index(
        "ix_notifications_user_created_at_id",
        "notifications",
        ["user_id", sa.text("created_at DESC"), "id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_user_created_at_id", table_name="notifications", schema="public"
    )
    op.drop_table("notifications", schema="public")
