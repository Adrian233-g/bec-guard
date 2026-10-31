from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MailboxConnection(Base):
    """Non-secret progress of a mailbox provisioning operation."""

    __tablename__ = "mailbox_connections"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    mailbox_id: Mapped[UUID] = mapped_column(
        ForeignKey("mailboxes.id", ondelete="RESTRICT"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    imap_credential_id: Mapped[str] = mapped_column(String(16), nullable=False)
    automation_credential_id: Mapped[str] = mapped_column(String(16), nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    needs_reconciliation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_mailbox_connections_mailbox_id", mailbox_id, unique=True),
        CheckConstraint(
            "stage IN ('allocated', 'imap-created', 'imap-verified', 'automation-created', "
            "'workflow-created', 'active', 'workflow-unpublished', 'workflow-deleted', "
            "'imap-deleted', 'automation-deleted')",
            name="stage",
        ),
    )
