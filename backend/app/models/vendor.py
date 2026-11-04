from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, Uuid, func, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.context_validation import normalize_domain
from app.core.identity import validate_identity_email
from app.models.base import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    bank_account_reference: Mapped[str | None] = mapped_column(String(256))
    responsibilities: Mapped[str | None] = mapped_column(Text)
    allowed_actions: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_vendors_domain_lower", func.lower(domain), unique=True),
        CheckConstraint(
            "responsibilities IS NULL OR length(responsibilities) <= 2000", name="responsibilities"
        ),
        CheckConstraint(
            "allowed_actions IS NULL OR (jsonb_typeof(allowed_actions) = 'array' AND "
            'allowed_actions <@ \'["PAYMENT_REQUEST", "BANK_ACCOUNT_CHANGE", '
            '"SENSITIVE_DATA_REQUEST"]\'::jsonb)',
            name="allowed_actions",
        ),
    )

    @validates("domain")
    def normalize_hostname(self, _key: str, value: str) -> str:
        return normalize_domain(value)

    @validates("contact_email")
    def normalize_email(self, _key: str, value: str | None) -> str | None:
        return validate_identity_email(value) if value is not None else None
