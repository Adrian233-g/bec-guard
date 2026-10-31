from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from app.models.enums import AlertStatus, NotificationKind, RiskLevel
from app.schemas.analysis import Score


class NotificationResponse(BaseModel):
    id: UUID
    alert_id: UUID
    kind: NotificationKind
    read_at: AwareDatetime | None
    created_at: AwareDatetime
    alert_status: AlertStatus
    risk_level: RiskLevel
    risk_score: Score
    subject: str
    sender_name: str | None
    sender_email: str


class UnreadCountResponse(BaseModel):
    count: int


class ReadAllResponse(BaseModel):
    updated: int
