from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.identity import normalize_email
from app.models.base import Base


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default="gmail")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISCONNECTED', 'ERROR')", name="status"),
        CheckConstraint("provider IN ('gmail', 'imap', 'other')", name="provider"),
        Index("uq_mailboxes_email_lower", func.lower(email_address), unique=True),
        Index("uq_mailboxes_user_id", user_id, unique=True),
    )

    @validates("email_address")
    def normalize_identity(self, _key: str, value: str) -> str:
        return normalize_email(value)
