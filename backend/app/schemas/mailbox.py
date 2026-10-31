from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr

from app.models.enums import MailboxProvider, MailboxStatus


class MailboxCreate(BaseModel):
    email_address: EmailStr
    provider: MailboxProvider = MailboxProvider.GMAIL


class MailboxUpdate(BaseModel):
    status: MailboxStatus | None = None


class MailboxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email_address: str
    provider: str
    status: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
