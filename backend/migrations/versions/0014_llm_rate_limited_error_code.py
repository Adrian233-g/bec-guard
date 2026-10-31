"""Distinguish provider rate limiting from other LLM failures."""

import sqlalchemy as sa
from alembic import op

revision = "0014_llm_rate_limited_error_code"
down_revision = "0013_notifications"
branch_labels = None
depends_on = None

OLD_VALUES = (
    "error_code IN ('LLM_NOT_CONFIGURED', 'LLM_TIMEOUT', "
    "'LLM_PROVIDER_ERROR', 'LLM_INVALID_OUTPUT')"
)
NEW_VALUES = (
    "error_code IN ('LLM_NOT_CONFIGURED', 'LLM_TIMEOUT', 'LLM_RATE_LIMITED', "
    "'LLM_PROVIDER_ERROR', 'LLM_INVALID_OUTPUT')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_email_analysis_error_code"), "email_analysis", schema="public")
    op.create_check_constraint(
        op.f("ck_email_analysis_error_code"), "email_analysis", NEW_VALUES, schema="public"
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM public.email_analysis "
                "WHERE error_code = 'LLM_RATE_LIMITED')"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while LLM_RATE_LIMITED analyses exist")
    op.drop_constraint(op.f("ck_email_analysis_error_code"), "email_analysis", schema="public")
    op.create_check_constraint(
        op.f("ck_email_analysis_error_code"), "email_analysis", OLD_VALUES, schema="public"
    )
