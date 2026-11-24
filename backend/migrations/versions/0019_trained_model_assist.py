"""Allow an explicitly pinned classifier to raise a rules fallback score."""

import sqlalchemy as sa
from alembic import op

revision = "0019_trained_model_assist"
down_revision = "0018_analysis_score_breakdown"
branch_labels = None
depends_on = None

OLD = (
    "(status = 'COMPLETED' AND semantic_score IS NOT NULL AND risk_score IS NOT NULL "
    "AND risk_level IS NOT NULL AND summary IS NOT NULL AND recommended_action IS NOT NULL "
    "AND provider IS NOT NULL AND model IS NOT NULL AND error_code IS NULL) OR "
    "(status = 'FALLBACK' AND semantic_score IS NULL AND risk_score IS NOT NULL "
    "AND risk_score = deterministic_score AND risk_level IS NOT NULL "
    "AND summary IS NOT NULL AND recommended_action IS NOT NULL AND error_code IS NOT NULL) OR "
    "(status = 'ERROR' AND semantic_score IS NULL AND risk_score IS NULL "
    "AND risk_level IS NULL AND bec_type IS NULL AND summary IS NULL "
    "AND recommended_action IS NULL AND error_code IS NOT NULL)"
)
NEW = OLD.replace(
    "risk_score = deterministic_score AND risk_level",
    "(risk_score = deterministic_score OR "
    "(score_breakdown->>'model_mode' = 'assist' AND "
    "risk_score = GREATEST(deterministic_score, "
    "(score_breakdown->>'model_score')::integer))) AND risk_level",
)


def _replace(sql: str) -> None:
    op.drop_constraint(op.f("ck_email_analysis_result_status"), "email_analysis", schema="public")
    op.create_check_constraint(
        op.f("ck_email_analysis_result_status"), "email_analysis", sql, schema="public"
    )


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM public.email_analysis WHERE status = 'FALLBACK' "
            "AND risk_score <> deterministic_score)"
        )
    ):
        raise RuntimeError("Cannot downgrade while assisted fallback analyses exist")
    _replace(OLD)
