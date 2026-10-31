"""Derive a separate automation credential for each trusted mailbox connector."""

import hashlib
import hmac
from uuid import UUID


def connector_token(master_key: str, mailbox_id: UUID) -> str:
    if len(master_key) < 32:
        raise ValueError("Automation key must contain at least 32 characters")
    identity = mailbox_id.hex
    signature = hmac.new(
        master_key.encode(), b"bec-guard-connector-v1:" + identity.encode(), hashlib.sha256
    ).hexdigest()
    return f"bg1.{identity}.{signature}"


def verify_connector_token(master_key: str, token: str) -> UUID | None:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "bg1" or len(parts[1]) != 32:
        return None
    try:
        mailbox_id = UUID(hex=parts[1])
        expected = connector_token(master_key, mailbox_id)
    except ValueError:
        return None
    if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        return None
    return mailbox_id
