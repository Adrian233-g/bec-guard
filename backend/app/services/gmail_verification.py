"""Verify access to Gmail without reading or changing messages."""

import imaplib
import ssl


class GmailAuthenticationFailed(Exception):
    pass


class GmailUnavailable(Exception):
    pass


def verify_gmail_access(address: str, app_password: str) -> None:
    connection = None
    authenticated = False
    try:
        connection = imaplib.IMAP4_SSL(
            "imap.gmail.com", 993, ssl_context=ssl.create_default_context(), timeout=10
        )
        try:
            status, _ = connection.login(address, app_password.replace(" ", ""))
        except imaplib.IMAP4.abort:
            raise GmailUnavailable from None
        except imaplib.IMAP4.error:
            raise GmailAuthenticationFailed from None
        if status != "OK":
            raise GmailAuthenticationFailed
        authenticated = True
        # Selecting read-only verifies that the INBOX is accessible; do not fetch mail.
        status, _ = connection.select("INBOX", readonly=True)
        if status != "OK":
            raise GmailUnavailable
    except GmailAuthenticationFailed, GmailUnavailable:
        raise
    except OSError, ssl.SSLError, imaplib.IMAP4.error, UnicodeError, ValueError:
        raise GmailUnavailable from None
    finally:
        if connection is not None:
            try:
                if authenticated:
                    connection.logout()
                else:
                    connection.shutdown()
            except OSError, imaplib.IMAP4.error:
                pass
