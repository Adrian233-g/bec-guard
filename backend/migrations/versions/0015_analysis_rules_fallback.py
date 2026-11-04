"""Persist an explicitly limited rules-only analysis when semantic analysis fails."""

import sqlalchemy as sa
from alembic import op

revision = "0015_analysis_rules_fallback"
down_revision = "0014_llm_rate_limited_error_code"
branch_labels = None
depends_on = None

OLD_STATUS = "status IN ('COMPLETED', 'ERROR')"
NEW_STATUS = "status IN ('COMPLETED', 'FALLBACK', 'ERROR')"
OLD_RESULT = (
    "(status = 'COMPLETED' AND semantic_score IS NOT NULL AND risk_score IS NOT NULL "
    "AND risk_level IS NOT NULL AND summary IS NOT NULL AND recommended_action IS NOT NULL "
    "AND provider IS NOT NULL AND model IS NOT NULL AND error_code IS NULL) OR "
    "(status = 'ERROR' AND semantic_score IS NULL AND risk_score IS NULL "
    "AND risk_level IS NULL AND bec_type IS NULL AND summary IS NULL "
    "AND recommended_action IS NULL AND error_code IS NOT NULL)"
)
NEW_RESULT = OLD_RESULT + (
    " OR (status = 'FALLBACK' AND semantic_score IS NULL AND risk_score IS NOT NULL "
    "AND risk_score = deterministic_score AND risk_level IS NOT NULL "
    "AND summary IS NOT NULL AND recommended_action IS NOT NULL AND error_code IS NOT NULL)"
)


def replace(name: str, sql: str) -> None:
    op.drop_constraint(op.f(f"ck_email_analysis_{name}"), "email_analysis", schema="public")
    op.create_check_constraint(
        op.f(f"ck_email_analysis_{name}"), "email_analysis", sql, schema="public"
    )


def upgrade() -> None:
    replace("status", NEW_STATUS)
    replace("result_status", NEW_RESULT)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM public.email_analysis WHERE status = 'FALLBACK')")
    ):
        raise RuntimeError("Cannot downgrade while rules-only analyses exist")
    replace("result_status", OLD_RESULT)
    replace("status", OLD_STATUS)
