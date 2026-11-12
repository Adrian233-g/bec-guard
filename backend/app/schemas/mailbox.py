from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    model_validator,
)

from app.models.enums import MailboxProvider, MailboxStatus


class MailboxCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_address: EmailStr
    provider: MailboxProvider = MailboxProvider.GMAIL


class MailboxUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MailboxStatus

    @model_validator(mode="after")
    def status_required(self):
        if "status" not in self.model_fields_set:
            raise ValueError("Status required")
        return self


class MailboxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email_address: str
    provider: str
    status: str
    connection_stage: str | None = None
    needs_reconciliation: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime


class GmailVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_password: SecretStr = Field(min_length=1, max_length=128)


class GmailVerificationResponse(BaseModel):
    verified: bool
