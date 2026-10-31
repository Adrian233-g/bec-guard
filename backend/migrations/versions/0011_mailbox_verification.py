"""Quarantine unverified mailboxes and require review of previous ownership."""

from uuid import UUID

import sqlalchemy as sa
from alembic import context, op
from email_validator import EmailNotValidError, validate_email

revision = "0011_mailbox_verification"
down_revision = "0010_mailboxes_and_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    args = context.get_x_argument(as_dictionary=True)
    has_emails = bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM public.emails)")).scalar()
    verified_mailbox = None
    owner = args.get("legacy_owner_id")
    address = args.get("legacy_mailbox_address")
    if owner or address:
        try:
            owner_id = UUID(owner or "")
            email = validate_email(address or "", check_deliverability=False).normalized.lower()
        except ValueError, EmailNotValidError:
            raise RuntimeError("Invalid explicit legacy mailbox owner or address") from None
        verified_mailbox = bind.execute(
            sa.text(
                "SELECT id FROM public.mailboxes WHERE user_id=:owner "
                "AND lower(email_address)=:email"
            ),
            {"owner": owner_id, "email": email},
        ).scalar()
        if has_emails and (
            verified_mailbox is None
            or bind.execute(
                sa.text("SELECT EXISTS (SELECT 1 FROM public.emails WHERE mailbox_id != :id)"),
                {"id": verified_mailbox},
            ).scalar()
        ):
            raise RuntimeError("Existing emails do not all match the confirmed legacy mailbox")
    elif has_emails and args.get("confirm_existing_ownership") != "true":
        raise RuntimeError(
            "Existing mailbox ownership requires review and -x confirm_existing_ownership=true"
        )

    op.drop_constraint(op.f("ck_mailboxes_status"), "mailboxes", schema="public")
    op.create_check_constraint(
        op.f("ck_mailboxes_status"),
        "mailboxes",
        "status IN ('PENDING', 'ACTIVE', 'DISCONNECTED', 'ERROR')",
        schema="public",
    )
    op.alter_column("mailboxes", "status", server_default="PENDING", schema="public")
    op.drop_index("uq_mailboxes_email_lower", table_name="mailboxes", schema="public")
    op.create_index(
        "uq_mailboxes_email_lower",
        "mailboxes",
        [sa.text("lower(email_address)")],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    # Existing ACTIVE rows were not verified by the old API. Quarantine all of
    # them; only an explicitly confirmed existing connector can remain active.
    bind.execute(sa.text("UPDATE public.mailboxes SET status='PENDING' WHERE status='ACTIVE'"))
    if args.get("legacy_connector_confirmed") == "true":
        if not verified_mailbox:
            raise RuntimeError("Confirmed legacy connector requires explicit owner and address")
        bind.execute(
            sa.text("UPDATE public.mailboxes SET status='ACTIVE' WHERE id=:id"),
            {"id": verified_mailbox},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM public.mailboxes WHERE status='PENDING')")
    ).scalar():
        raise RuntimeError("Cannot downgrade while unverified mailboxes exist")
    op.drop_index("uq_mailboxes_email_lower", table_name="mailboxes", schema="public")
    op.create_index(
        "uq_mailboxes_email_lower",
        "mailboxes",
        [sa.text("lower(email_address)")],
        unique=True,
        schema="public",
    )
    op.alter_column("mailboxes", "status", server_default="ACTIVE", schema="public")
    op.drop_constraint(op.f("ck_mailboxes_status"), "mailboxes", schema="public")
    op.create_check_constraint(
        op.f("ck_mailboxes_status"),
        "mailboxes",
        "status IN ('ACTIVE', 'DISCONNECTED', 'ERROR')",
        schema="public",
    )
