"""Record analysis processing duration without storing private content."""

import sqlalchemy as sa
from alembic import op

revision = "0017_analysis_duration"
down_revision = "0016_context_responsibilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_analysis",
        sa.Column("duration_ms", sa.Float(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        op.f("ck_email_analysis_duration_ms"),
        "email_analysis",
        "duration_ms IS NULL OR duration_ms >= 0",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_email_analysis_duration_ms"), "email_analysis", schema="public")
    op.drop_column("email_analysis", "duration_ms", schema="public")
