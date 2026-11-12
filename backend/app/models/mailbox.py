from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.identity import normalize_email
from app.models.base import Base
from app.models.mailbox_connection import MailboxConnection


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default="gmail")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    connection: Mapped[MailboxConnection | None] = relationship(
        back_populates="mailbox", uselist=False
    )

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'ACTIVE', 'DISCONNECTED', 'ERROR')", name="status"),
        CheckConstraint("provider IN ('gmail', 'imap', 'other')", name="provider"),
        Index(
            "uq_mailboxes_email_lower",
            func.lower(email_address),
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("uq_mailboxes_user_id", user_id, unique=True),
    )

    @validates("email_address")
    def normalize_identity(self, _key: str, value: str) -> str:
        return normalize_email(value)

    @property
    def connection_stage(self) -> str | None:
        return self.connection.stage if self.connection else None

    @property
    def needs_reconciliation(self) -> bool:
        return bool(self.connection and self.connection.needs_reconciliation)
