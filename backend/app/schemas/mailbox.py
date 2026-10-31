from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, model_validator

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
    created_at: AwareDatetime
    updated_at: AwareDatetime
