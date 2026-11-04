from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models import BECAlert, Email, EmailAnalysis, Mailbox, Notification, User
from app.models.enums import NotificationKind, Role


def create_alert_notifications(session: Session, alert, analysis: EmailAnalysis) -> None:
    """Queue in-app notices for the mailbox owner and the active security team.

    Part of the alert transaction: a failure rolls back the alert as well.
    The unique constraint makes a repeated call harmless.
    """
    email = session.get(Email, analysis.email_id)
    mailbox = session.get(Mailbox, email.mailbox_id) if email else None
    access = [User.role.in_((Role.ADMIN, Role.ANALYST))]
    if mailbox is not None:
        access.append(User.id == mailbox.user_id)
    recipients = set(session.scalars(select(User.id).where(User.is_active.is_(True), or_(*access))))
    session.add_all(
        Notification(user_id=user_id, alert_id=alert.id, kind=NotificationKind.BEC_ALERT)
        for user_id in recipients
    )


def accessible_notification_ids(user_id: UUID):
    """Do not expose old security notices after a recipient loses alert access."""
    return (
        select(Notification.id)
        .join(BECAlert, Notification.alert_id == BECAlert.id)
        .join(EmailAnalysis, BECAlert.analysis_id == EmailAnalysis.id)
        .join(Email, EmailAnalysis.email_id == Email.id)
        .join(Mailbox, Mailbox.id == Email.mailbox_id)
        .join(User, User.id == Notification.user_id)
        .where(
            Notification.user_id == user_id,
            User.is_active.is_(True),
            or_(User.role.in_((Role.ADMIN, Role.ANALYST)), Mailbox.user_id == user_id),
        )
    )


def list_notifications(
    session: Session,
    *,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
):
    statement = (
        select(
            Notification.id,
            Notification.alert_id,
            Notification.kind,
            Notification.read_at,
            Notification.created_at,
            BECAlert.status.label("alert_status"),
            EmailAnalysis.risk_level,
            EmailAnalysis.risk_score,
            Email.subject,
            Email.sender_name,
            Email.sender_email,
        )
        .join(BECAlert, Notification.alert_id == BECAlert.id)
        .join(EmailAnalysis, BECAlert.analysis_id == EmailAnalysis.id)
        .join(Email, EmailAnalysis.email_id == Email.id)
        .where(Notification.id.in_(accessible_notification_ids(user_id)))
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    return session.execute(statement).mappings().all()


def unread_count(session: Session, *, user_id: UUID) -> int:
    return session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.id.in_(accessible_notification_ids(user_id)),
            Notification.read_at.is_(None),
        )
    )


def mark_read(session: Session, *, user_id: UUID, notification_id: UUID) -> bool:
    """Mark only a notification owned by the caller; never reveal others."""
    notification = session.scalar(
        select(Notification)
        .where(
            Notification.id == notification_id,
            Notification.id.in_(accessible_notification_ids(user_id)),
        )
        .with_for_update()
    )
    if notification is None:
        return False
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        session.commit()
    return True


def mark_all_read(session: Session, *, user_id: UUID) -> int:
    result = session.execute(
        update(Notification)
        .where(
            Notification.id.in_(accessible_notification_ids(user_id)),
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount
