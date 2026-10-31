from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import MailboxProvider, MailboxStatus
from app.schemas.email import EmailIngestRequest
from app.schemas.mailbox import MailboxCreate, MailboxUpdate


def test_mailbox_create_schema_normalization():
    create = MailboxCreate(email_address="USER.NAME@EXAMPLE.COM")
    assert create.email_address.lower() == "user.name@example.com"
    assert create.provider == MailboxProvider.GMAIL


def test_mailbox_create_invalid_email():
    with pytest.raises(ValidationError):
        MailboxCreate(email_address="not-an-email")


def test_mailbox_update_schema():
    update = MailboxUpdate(status=MailboxStatus.DISCONNECTED)
    assert update.status == MailboxStatus.DISCONNECTED

    with pytest.raises(ValidationError):
        MailboxUpdate()
    with pytest.raises(ValidationError):
        MailboxUpdate(status=None)


def test_email_ingest_request_accepts_valid_mailbox_id(email_payload):
    mb_id = uuid4()
    req = EmailIngestRequest(**{**email_payload, "mailbox_id": mb_id})
    assert req.mailbox_id == mb_id


def test_email_ingest_request_rejects_invalid_mailbox_id(email_payload):
    with pytest.raises(ValidationError):
        EmailIngestRequest(**{**email_payload, "mailbox_id": "not-a-uuid"})
