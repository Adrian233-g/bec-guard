"""Store an optional role description and explicitly configured request categories."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016_context_responsibilities"
down_revision = "0015_analysis_rules_fallback"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("executive_contacts", "vendors"):
        op.add_column(
            table, sa.Column("responsibilities", sa.Text(), nullable=True), schema="public"
        )
        op.add_column(table, sa.Column("allowed_actions", JSONB(), nullable=True), schema="public")
        op.create_check_constraint(
            op.f(f"ck_{table}_allowed_actions"),
            table,
            "allowed_actions IS NULL OR (jsonb_typeof(allowed_actions) = 'array' AND "
            'allowed_actions <@ \'["PAYMENT_REQUEST", "BANK_ACCOUNT_CHANGE", '
            '"SENSITIVE_DATA_REQUEST"]\'::jsonb)',
            schema="public",
        )
        op.create_check_constraint(
            op.f(f"ck_{table}_responsibilities"),
            table,
            "responsibilities IS NULL OR length(responsibilities) <= 2000",
            schema="public",
        )


def downgrade():
    connection = op.get_bind()
    for table in ("executive_contacts", "vendors"):
        if connection.scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM public.{table} WHERE "
                "responsibilities IS NOT NULL OR allowed_actions IS NOT NULL)"
            )
        ):
            raise RuntimeError("Cannot downgrade while context responsibilities are configured")
    for table in ("executive_contacts", "vendors"):
        op.drop_constraint(op.f(f"ck_{table}_allowed_actions"), table, schema="public")
        op.drop_constraint(op.f(f"ck_{table}_responsibilities"), table, schema="public")
        op.drop_column(table, "allowed_actions", schema="public")
        op.drop_column(table, "responsibilities", schema="public")
