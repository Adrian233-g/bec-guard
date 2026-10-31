"""Explicit, repeatable demo context and unanalysed emails. Never invokes an LLM."""

import argparse
import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.core.identity import validate_identity_email
from app.models import Email, ExecutiveContact, Mailbox, Role, User, Vendor
from app.schemas.email import EmailIngestRequest
from app.schemas.organizational_context import ExecutiveContactCreate, VendorCreate
from app.scripts.demo_data import EXECUTIVES, MESSAGES, VENDORS
from app.services.email_ingestion import ingest_email
from app.services.organizational_context import (
    create_context,
    find_executive_by_email,
    find_vendor_by_domain,
)


def seed_demo(session: Session, *, actor: User) -> dict:
    if not actor.is_active or actor.role != Role.ADMIN:
        raise ValueError("An active ADMIN is required")
    # Validate the entire fixture before any writes. No dataset imports/annotations.
    executives = [ExecutiveContactCreate(**data) for data in EXECUTIVES]
    vendors = [VendorCreate(**data) for data in VENDORS]
    now = datetime.now(UTC)
    emails = [
        EmailIngestRequest(
            message_id=f"<bec-guard-demo-v1-{index:03d}@demo.becguard.example>",
            to_recipients=["tesoreria@oriona-demo.example"],
            received_at=now - timedelta(minutes=index - 1),
            **{
                "authentication_results": "mx.demo.example; spf=pass; dkim=pass; dmarc=pass",
                **data,
                "subject": f"[DEMO {index:02d}] {data['subject']}",
            },
        )
        for index, data in enumerate(MESSAGES, 1)
    ]
    counts = {key: {"created": 0, "existing": 0} for key in ("executives", "vendors", "emails")}
    for data in executives:
        exists = find_executive_by_email(session, data.email, include_inactive=True)
        if exists is not None:
            counts["executives"]["existing"] += 1
            continue
        try:
            create_context(session, ExecutiveContact(**data.model_dump()), actor=actor)
            counts["executives"]["created"] += 1
        except HTTPException as error:
            if error.status_code != 409:
                raise
            counts["executives"]["existing"] += 1
    for data in vendors:
        exists = find_vendor_by_domain(session, data.domain, include_inactive=True)
        if exists is not None:
            counts["vendors"]["existing"] += 1
            continue
        try:
            create_context(session, Vendor(**data.model_dump()), actor=actor)
            counts["vendors"]["created"] += 1
        except HTTPException as error:
            if error.status_code != 409:
                raise
            counts["vendors"]["existing"] += 1
    demo_mailbox = session.scalar(select(Mailbox).where(Mailbox.user_id == actor.id))
    if demo_mailbox is None:
        demo_mailbox = Mailbox(
            user_id=actor.id,
            email_address="tesoreria@oriona-demo.example",
            provider="other",
            status="PENDING",
        )
        session.add(demo_mailbox)
        session.flush()

    for data in emails:
        exists = session.scalar(
            select(Email.id).where(
                Email.mailbox_id == demo_mailbox.id,
                Email.message_id == data.message_id,
            )
        )
        if exists is not None:
            counts["emails"]["existing"] += 1
            continue
        try:
            ingest_email(session, data, mailbox_id=demo_mailbox.id, actor=actor)
            counts["emails"]["created"] += 1
        except HTTPException as error:
            if error.status_code != 409:
                raise
            counts["emails"]["existing"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-demo", action="store_true")
    parser.add_argument("--actor-email", required=True, help="Existing active ADMIN; no password")
    args = parser.parse_args(argv)
    if not args.confirm_demo:
        parser.error("--confirm-demo is required; no database was accessed")
    engine = None
    try:
        email = validate_identity_email(args.actor_email)
        engine = create_database_engine(Settings())
        with create_session_factory(engine)() as session:
            actor = session.scalar(select(User).where(User.email == email))
            if actor is None:
                raise ValueError("Create an initial ADMIN with create_admin first")
            result = seed_demo(session, actor=actor)
        print(json.dumps(result))
        print("Demo ready. Open Correos and choose Analizar correo. No LLM was called.")
        return 0
    except ValueError, SQLAlchemyError, HTTPException:
        print(
            "Demo seed failed: verify the active ADMIN, configuration and migrations. "
            "Existing records are preserved; rerunning resumes missing records."
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
