"""Register domain models in the shared metadata used by Alembic."""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.bec_alert import BECAlert
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.enums import Role
from app.models.executive_contact import ExecutiveContact
from app.models.mailbox import Mailbox
from app.models.mailbox_connection import MailboxConnection
from app.models.notification import Notification
from app.models.user import User
from app.models.vendor import Vendor

__all__ = [
    "AuditLog",
    "Base",
    "BECAlert",
    "Email",
    "EmailAnalysis",
    "ExecutiveContact",
    "Mailbox",
    "MailboxConnection",
    "Notification",
    "Role",
    "User",
    "Vendor",
]
