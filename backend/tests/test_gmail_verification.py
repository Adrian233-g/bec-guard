import imaplib
from unittest.mock import Mock

import pytest

from app.core.tokens import create_access_token
from app.models import Mailbox, Role, User
from app.services.gmail_verification import (
    GmailAuthenticationFailed,
    GmailUnavailable,
    verify_gmail_access,
)


def test_verification_connects_with_tls_read_only_and_never_fetches(monkeypatch):
    connection = Mock()
    connection.login.return_value = ("OK", [])
    connection.select.return_value = ("OK", [])
    factory = Mock(return_value=connection)
    monkeypatch.setattr("app.services.gmail_verification.imaplib.IMAP4_SSL", factory)
    verify_gmail_access("person@gmail.com", "abcd efgh ijkl mnop")
    args, kwargs = factory.call_args
    assert args == ("imap.gmail.com", 993)
    assert kwargs["ssl_context"].check_hostname is True
    assert kwargs["timeout"] == 10
    connection.login.assert_called_once_with("person@gmail.com", "abcdefghijklmnop")
    connection.select.assert_called_once_with("INBOX", readonly=True)
    connection.fetch.assert_not_called()
    connection.logout.assert_called_once()


def test_authentication_failure_closes_connection_without_leaking_password(monkeypatch):
    connection = Mock()
    connection.login.side_effect = imaplib.IMAP4.error("secret-in-provider-error")
    monkeypatch.setattr(
        "app.services.gmail_verification.imaplib.IMAP4_SSL", lambda *a, **k: connection
    )
    with pytest.raises(GmailAuthenticationFailed) as error:
        verify_gmail_access("person@gmail.com", "secret-in-provider-error")
    assert "secret-in-provider-error" not in str(error.value)
    connection.select.assert_not_called()
    connection.shutdown.assert_called_once()


def test_network_failure_is_distinct_from_invalid_password(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("secret-in-network-error")

    monkeypatch.setattr("app.services.gmail_verification.imaplib.IMAP4_SSL", fail)
    with pytest.raises(GmailUnavailable) as error:
        verify_gmail_access("person@gmail.com", "secret-in-network-error")
    assert "secret-in-network-error" not in str(error.value)


@pytest.mark.integration
def test_only_mailbox_owner_can_verify_and_no_state_or_password_is_saved(
    monkeypatch, api_client, db_session, account, auth_settings
):
    mailbox = db_session.query(Mailbox).filter_by(user_id=account.id).one()
    mailbox.status = "PENDING"
    other = User(
        name="Other", email="other-gmail@example.com", password_hash="hash", role=Role.EMPLOYEE
    )
    db_session.add(other)
    db_session.commit()
    verify = Mock()
    monkeypatch.setattr("app.api.mailboxes.verify_gmail_access", verify)
    owner_headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, auth_settings)}"}
    path = f"/api/mailboxes/{mailbox.id}/verify-gmail"
    assert (
        api_client.post(path, json={"app_password": "not-yours"}, headers=other_headers).status_code
        == 404
    )
    verify.assert_not_called()
    response = api_client.post(path, json={"app_password": "private-secret"}, headers=owner_headers)
    assert response.status_code == 200 and response.json() == {"verified": True}
    assert "private-secret" not in response.text
    verify.assert_called_once_with(mailbox.email_address, "private-secret")
    db_session.refresh(mailbox)
    assert mailbox.status == "PENDING"


def test_imap_disconnect_during_login_is_unavailable(monkeypatch):
    connection = Mock()
    connection.login.side_effect = imaplib.IMAP4.abort("disconnected")
    monkeypatch.setattr(
        "app.services.gmail_verification.imaplib.IMAP4_SSL", lambda *args, **kwargs: connection
    )
    with pytest.raises(GmailUnavailable):
        verify_gmail_access("person@gmail.com", "password")
    connection.shutdown.assert_called_once()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("error", "status"), [(GmailAuthenticationFailed(), 400), (GmailUnavailable(), 503)]
)
def test_verify_api_returns_sanitized_failures(
    monkeypatch, api_client, db_session, account, auth_settings, error, status
):
    mailbox = db_session.query(Mailbox).filter_by(user_id=account.id).one()

    def fail(*args):
        raise error

    monkeypatch.setattr("app.api.mailboxes.verify_gmail_access", fail)
    headers = {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}
    response = api_client.post(
        f"/api/mailboxes/{mailbox.id}/verify-gmail",
        json={"app_password": "very-private-password"},
        headers=headers,
    )
    assert response.status_code == status
    assert "very-private-password" not in response.text
