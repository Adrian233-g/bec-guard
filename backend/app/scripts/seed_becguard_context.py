"""Add the fictional BEC Guard organization without replacing existing context."""

import argparse

from sqlalchemy import select

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.models import ExecutiveContact, Role, User, Vendor
from app.schemas.organizational_context import ExecutiveContactCreate, VendorCreate
from app.services.organizational_context import (
    create_context,
    find_executive_by_email,
    find_vendor_by_domain,
)

EXECUTIVES = [
    dict(
        name="Valeria Montes",
        position="Directora general",
        department="Dirección",
        email="valeria.montes@becguard.com",
        responsibilities="Dirige la estrategia; solicita pagos con aprobación financiera.",
        allowed_actions=["PAYMENT_REQUEST"],
    ),
    dict(
        name="Mateo Rivas",
        position="Director financiero",
        department="Finanzas",
        email="mateo.rivas@becguard.com",
        responsibilities="Coordina tesorería, pagos y cambios bancarios con doble validación.",
        allowed_actions=["PAYMENT_REQUEST", "BANK_ACCOUNT_CHANGE"],
    ),
    dict(
        name="Camila Torres",
        position="Directora de operaciones",
        department="Operaciones",
        email="camila.torres@becguard.com",
        responsibilities="Coordina proveedores y operaciones; Finanzas gestiona los pagos.",
        allowed_actions=[],
    ),
    dict(
        name="Gabriel Luna",
        position="Director de tecnología",
        department="Tecnología",
        email="gabriel.luna@becguard.com",
        responsibilities="Dirige tecnología y seguridad; no solicita contraseñas por correo.",
        allowed_actions=[],
    ),
]
VENDORS = [
    dict(
        name="Andes Nube",
        domain="andes-nube.example",
        contact_email="facturacion@andes-nube.example",
        responsibilities="Provee infraestructura en la nube y envía facturas.",
        allowed_actions=["PAYMENT_REQUEST"],
    ),
    dict(
        name="Quipu Suministros",
        domain="quipu-suministros.example",
        contact_email="cuentas@quipu-suministros.example",
        responsibilities="Provee equipos y coordina facturación y cambios bancarios verificables.",
        allowed_actions=["PAYMENT_REQUEST", "BANK_ACCOUNT_CHANGE"],
    ),
    dict(
        name="Llama Digital",
        domain="llama-digital.example",
        contact_email="soporte@llama-digital.example",
        responsibilities="Brinda soporte de software; nunca solicita contraseñas por correo.",
        allowed_actions=[],
    ),
    dict(
        name="Costa Logística",
        domain="costa-logistica.example",
        contact_email="operaciones@costa-logistica.example",
        responsibilities="Coordina entregas y estado de envíos; no gestiona datos bancarios.",
        allowed_actions=[],
    ),
]


def seed(session, actor):
    if not actor or not actor.is_active or actor.role != Role.ADMIN:
        raise ValueError("Active administrator required")
    executives = [ExecutiveContactCreate(**row) for row in EXECUTIVES]
    vendors = [VendorCreate(**row) for row in VENDORS]
    counts = {"executives_created": 0, "vendors_created": 0, "existing": 0}
    for schema, model, lookup, identity, key in (
        (executives, ExecutiveContact, find_executive_by_email, "email", "executives_created"),
        (vendors, Vendor, find_vendor_by_domain, "domain", "vendors_created"),
    ):
        for row in schema:
            if lookup(session, getattr(row, identity), include_inactive=True):
                counts["existing"] += 1
            else:
                create_context(session, model(**row.model_dump()), actor=actor)
                counts[key] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-email", required=True)
    parser.add_argument("--confirm-fictional", action="store_true", required=True)
    args = parser.parse_args()
    engine = create_database_engine(Settings())
    try:
        with create_session_factory(engine)() as session:
            actor = session.scalar(select(User).where(User.email == args.actor_email.lower()))
            print(seed(session, actor))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
