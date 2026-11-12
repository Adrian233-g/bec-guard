"""Persist the auditable score path without storing model prompts or email text."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018_analysis_score_breakdown"
down_revision = "0017_analysis_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_analysis",
        sa.Column("score_breakdown", JSONB(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        op.f("ck_email_analysis_score_breakdown_object"),
        "email_analysis",
        "score_breakdown IS NULL OR jsonb_typeof(score_breakdown) = 'object'",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_email_analysis_score_breakdown_object"),
        "email_analysis",
        schema="public",
    )
    op.drop_column("email_analysis", "score_breakdown", schema="public")
