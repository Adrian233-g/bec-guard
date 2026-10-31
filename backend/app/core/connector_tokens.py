"""Derive a credential scoped to one specific mailbox connection generation."""

import hashlib
import hmac
from uuid import UUID


def connector_token(master_key: str, mailbox_id: UUID, connection_id: UUID) -> str:
    if len(master_key) < 32:
        raise ValueError("Automation key must contain at least 32 characters")
    identity = f"{mailbox_id.hex}.{connection_id.hex}"
    signature = hmac.new(
        master_key.encode(), b"bec-guard-connector-v2:" + identity.encode(), hashlib.sha256
    ).hexdigest()
    return f"bg2.{identity}.{signature}"


def verify_connector_token(master_key: str, token: str) -> tuple[UUID, UUID] | None:
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "bg2" or len(parts[1]) != 32 or len(parts[2]) != 32:
        return None
    try:
        mailbox_id = UUID(hex=parts[1])
        connection_id = UUID(hex=parts[2])
        expected = connector_token(master_key, mailbox_id, connection_id)
    except ValueError:
        return None
    if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        return None
    return mailbox_id, connection_id
