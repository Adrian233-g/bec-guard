"""Generador reproducible de un corpus sintético candidato, no científico."""

import argparse
import hashlib
import json
import os
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.dataset import DatasetLabel, ExpectedBECType
from app.schemas.email import EmailIngestRequest

GENERATOR_VERSION = "bec-synthetic-v1"
SEED = 20261119
TOTAL_CASES = 500
EXPECTED_BEC = 120
EXPECTED_HARD_NEGATIVES = 100

_BASE_TIME = datetime(2026, 11, 1, tzinfo=UTC)
_RECIPIENT = "revision@luminaria.example"
_AUTH = "mx.luminaria.example; spf=pass; dkim=pass; dmarc=pass"

_EXECUTIVES = (
    ("Nora Prisma", "nora@luminaria.example"),
    ("Teo Bruma", "teo@luminaria.example"),
    ("Elia Nexo", "elia@luminaria.example"),
    ("Lian Delta", "lian@luminaria.example"),
)
_VENDORS = (
    ("Cobre Azul", "cobreazul.example", "facturas@cobreazul.example"),
    ("Papel Nube", "papelnube.example", "ventas@papelnube.example"),
    ("Circuito Prisma", "circuitoprisma.example", "soporte@circuitoprisma.example"),
    ("Ruta Violeta", "rutavioleta.example", "cobros@rutavioleta.example"),
)
_PLACES = (
    "Bogota",
    "Lima",
    "Quito",
    "Santiago",
    "Madrid",
    "Valencia",
    "Rosario",
    "Bilbao",
    "Asuncion",
    "Managua",
)
_QUALIFIERS = (
    "trimestral",
    "anual",
    "preliminar",
    "definitiva",
    "interna",
    "externa",
    "parcial",
    "regional",
    "provisional",
    "mensual",
)
_LOOKALIKE_SUFFIXES = ("1a", "aa", "4", "-secure", "-portal")

_BEC_SUBJECTS = {
    ExpectedBECType.EXECUTIVE_IMPERSONATION: (
        "Instruccion privada para el cierre {reference}",
        "Transferencia urgente solicitada por direccion {reference}",
        "Revision reservada del pago {reference}",
    ),
    ExpectedBECType.VENDOR_FRAUD: (
        "Actualizacion de datos del proveedor {reference}",
        "Cambio de cuenta para factura {reference}",
        "Confirmacion bancaria del expediente {reference}",
    ),
    ExpectedBECType.BANK_ACCOUNT_CHANGE: (
        "Nueva cuenta bancaria para pago {reference}",
        "Reemplazo de beneficiario de factura {reference}",
        "Gestion inmediata del pago {reference}",
    ),
    ExpectedBECType.SENSITIVE_DATA_REQUEST: (
        "Solicitud reservada de informacion {reference}",
        "Revision urgente de datos internos {reference}",
        "Documentacion confidencial del expediente {reference}",
    ),
}
_BEC_BODIES = {
    ExpectedBECType.EXECUTIVE_IMPERSONATION: (
        "Soy {executive}. Prepara una transferencia hoy y no consultes al equipo. "
        "La confirmacion se realizara despues del cierre.",
        "Habla {executive}. Necesito que autorices el pago de inmediato. "
        "Mantengamos la solicitud fuera del circuito habitual.",
        "La direccion necesita completar esta operacion ahora. "
        "Confirma cuando el banco haya procesado el movimiento.",
    ),
    ExpectedBECType.VENDOR_FRAUD: (
        "Somos {vendor} y necesitamos reemplazar la cuenta bancaria del pago. "
        "Por favor procesa el cambio antes del cierre.",
        "El proveedor solicita actualizar el beneficiario de la factura. "
        "Evita retrasos y confirma la operacion durante esta jornada.",
        "La cuenta registrada ya no debe utilizarse para este expediente. "
        "Envianos la confirmacion del nuevo destino.",
    ),
    ExpectedBECType.BANK_ACCOUNT_CHANGE: (
        "Necesitamos cambiar la cuenta bancaria asociada al pago. "
        "Gestiona el reemplazo con urgencia y confirma el resultado.",
        "Sustituye el beneficiario de la factura antes del cierre contable. "
        "No esperes a la proxima aprobacion del equipo.",
        "La transferencia debe enviarse a una cuenta nueva por una incidencia. "
        "Confirma el cambio por este mismo medio.",
    ),
    ExpectedBECType.SENSITIVE_DATA_REQUEST: (
        "Solicitamos el maestro completo de nomina para la revision. "
        "Envialo hoy junto con las credenciales del portal.",
        "Necesitamos los datos individuales del personal y las identificaciones. "
        "La solicitud es confidencial y debe resolverse de inmediato.",
        "Comparte las contrasenas del equipo para completar el alta. "
        "No incluyas a otros destinatarios en la respuesta.",
    ),
}
_LEGITIMATE_BODIES = (
    "La factura fue registrada correctamente y conserva las aprobaciones habituales. "
    "El expediente queda disponible para consulta.",
    "Adjuntamos el acta firmada por el comite de compras. "
    "No se modifican datos bancarios ni permisos de acceso.",
    "El inventario mensual fue conciliado sin diferencias pendientes. "
    "Cualquier comentario puede responderse por este medio.",
    "El calendario de entregas del proximo trimestre esta actualizado. "
    "La coordinacion seguira el procedimiento ordinario.",
)
_HARD_NEGATIVE_BODIES = (
    "El proveedor confirmado solicita actualizar la cuenta bancaria del expediente. "
    "La verificacion telefonica ya fue registrada por el comite.",
    "La direccion aprobo el cambio de beneficiario mediante el procedimiento habitual. "
    "No se requiere saltar controles ni enviar credenciales.",
    "La revision urgente del pago mantiene las aprobaciones y el contacto registrado. "
    "Confirma el tramite despues de verificarlo por el canal interno.",
)


def _token_line(rng: random.Random) -> str:
    """Adds non-semantic variation so unrelated cases are not near duplicates."""
    alphabet = "abcdefghijkmnopqrstuvwxyz23456789"
    tokens = ["q" + "".join(rng.choice(alphabet) for _ in range(10)) for _ in range(12)]
    return "Referencia tecnica " + " ".join(tokens) + "."


def _lookalike(domain: str, number: int) -> str:
    suffix = _LOOKALIKE_SUFFIXES[number % len(_LOOKALIKE_SUFFIXES)]
    host = domain.removesuffix(".example")
    return f"{host}{suffix}.example"


def _email(
    *,
    number: int,
    sender_name: str,
    sender_email: str,
    subject: str,
    body: str,
    thread_id: str,
) -> dict:
    value = {
        "message_id": f"<synthetic-{number:04d}@research.example>",
        "thread_id": thread_id,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "to_recipients": [_RECIPIENT],
        "subject": subject,
        "body_text": body,
        "authentication_results": _AUTH,
        "received_at": (_BASE_TIME + timedelta(minutes=number * 11)).isoformat(),
    }
    EmailIngestRequest.model_validate(value)
    return value


def _candidate(
    *,
    number: int,
    group_id: str,
    source_id: str,
    label: DatasetLabel,
    bec_type: ExpectedBECType | None,
    hard_negative: bool,
    sender_name: str,
    sender_email: str,
    subject: str,
    body: str,
    rationale: str,
    rng: random.Random,
) -> dict:
    return {
        "case_id": f"CASE-{number:04d}",
        "group_id": group_id,
        "source_id": source_id,
        "label": label.value,
        "expected_bec_type": bec_type.value if bec_type else None,
        "is_hard_negative": hard_negative,
        "label_rationale": rationale,
        "annotation_status": "GENERATED_CANDIDATE",
        "email": _email(
            number=number,
            sender_name=sender_name,
            sender_email=sender_email,
            subject=subject,
            body=f"{body} {_token_line(rng)}",
            thread_id=f"THREAD-{group_id}",
        ),
    }


def generate_candidates(seed: int = SEED) -> list[dict]:
    """Returns 500 labelled candidates; labels are hidden in the blind packet."""
    rng = random.Random(seed)
    records: list[dict] = []
    group_number = 0

    for bec_type in ExpectedBECType:
        if bec_type == ExpectedBECType.OTHER:
            continue
        for _ in range(15):
            group_number += 1
            group_id = f"GROUP-{group_number:04d}"
            source_id = f"SOURCE-{group_number:04d}"
            if bec_type == ExpectedBECType.EXECUTIVE_IMPERSONATION:
                executive, official_email = rng.choice(_EXECUTIVES)
                sender_name = executive
                official_domain = official_email.split("@", 1)[1]
                sender_domain = _lookalike(official_domain, group_number)
                sender_email = f"{executive.split()[0].lower()}{group_number}@{sender_domain}"
                vendor = ""
            elif bec_type == ExpectedBECType.VENDOR_FRAUD:
                vendor, domain, _contact = rng.choice(_VENDORS)
                sender_name = vendor
                sender_email = f"facturacion{group_number}@{_lookalike(domain, group_number)}"
                executive = ""
            else:
                sender_name = "Coordinacion administrativa"
                sender_email = f"gestion{group_number}@operaciones.example"
                executive = ""
                vendor = ""
            rationale = (
                f"Candidato generado para escenario {bec_type.value}; requiere revision ciega."
            )
            for copy in range(2):
                reference = f"REF-{group_number:04d}-{copy + 1}"
                subject = rng.choice(_BEC_SUBJECTS[bec_type]).format(reference=reference)
                body = rng.choice(_BEC_BODIES[bec_type]).format(
                    executive=executive, vendor=vendor, reference=reference
                )
                records.append(
                    _candidate(
                        number=len(records) + 1,
                        group_id=group_id,
                        source_id=source_id,
                        label=DatasetLabel.BEC,
                        bec_type=bec_type,
                        hard_negative=False,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        subject=subject,
                        body=body,
                        rationale=rationale,
                        rng=rng,
                    )
                )

    for hard_negative in (False, True):
        groups = 140 if not hard_negative else 50
        bodies = _LEGITIMATE_BODIES if not hard_negative else _HARD_NEGATIVE_BODIES
        for _ in range(groups):
            group_number += 1
            group_id = f"GROUP-{group_number:04d}"
            source_id = f"SOURCE-{group_number:04d}"
            vendor, _domain, contact = rng.choice(_VENDORS)
            sender_name = vendor if hard_negative else "Equipo administrativo"
            if hard_negative:
                local, domain = contact.split("@", 1)
                sender_email = f"{local}{group_number}@{domain}"
            else:
                sender_email = f"procesos{group_number}@operaciones.example"
            rationale = (
                "Legitimo con solicitud sensible validada; negativo dificil."
                if hard_negative
                else "Comunicacion legitima de rutina; requiere revision ciega."
            )
            for copy in range(2):
                reference = f"REF-{group_number:04d}-{copy + 1}"
                subject = (
                    f"Actualizacion verificada de datos {reference}"
                    if hard_negative
                    else f"Seguimiento administrativo {reference}"
                )
                records.append(
                    _candidate(
                        number=len(records) + 1,
                        group_id=group_id,
                        source_id=source_id,
                        label=DatasetLabel.LEGITIMATE,
                        bec_type=None,
                        hard_negative=hard_negative,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        subject=subject,
                        body=rng.choice(bodies),
                        rationale=rationale,
                        rng=rng,
                    )
                )

    rng.shuffle(records)
    for number, record in enumerate(records, 1):
        record["case_id"] = f"CASE-{number:04d}"
        record["email"]["message_id"] = f"<synthetic-{number:04d}@research.example>"
        record["email"]["received_at"] = (_BASE_TIME + timedelta(minutes=number * 11)).isoformat()
    return records


def _blind_record(record: dict) -> dict:
    return {
        "case_id": record["case_id"],
        "group_id": record["group_id"],
        "source_id": record["source_id"],
        "annotation_status": "PENDING_BLIND_REVIEW",
        "email": record["email"],
    }


def _write_exclusive(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(content)


def _jsonl(records: list[dict]) -> str:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )


def generate_package(output_dir: Path, *, seed: int = SEED) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    records = generate_candidates(seed)
    gold_content = _jsonl(records)
    blind_content = _jsonl([_blind_record(record) for record in records])
    gold_path = output_dir / "gold_reference.jsonl"
    blind_path = output_dir / "blind_review.jsonl"
    _write_exclusive(gold_path, gold_content)
    _write_exclusive(blind_path, blind_content)
    counts = Counter(record["label"] for record in records)
    type_counts = Counter(
        record["expected_bec_type"] for record in records if record["expected_bec_type"]
    )
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "status": "SYNTHETIC_CANDIDATE_REQUIRES_BLIND_REVIEW",
        "seed": seed,
        "total_cases": len(records),
        "groups": len({record["group_id"] for record in records}),
        "labels_reference": dict(counts),
        "bec_types_reference": dict(type_counts),
        "hard_negatives_reference": sum(record["is_hard_negative"] for record in records),
        "gold_reference_sha256": hashlib.sha256(gold_content.encode()).hexdigest(),
        "blind_review_sha256": hashlib.sha256(blind_content.encode()).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(),
        "gold_reference": gold_path.name,
        "blind_review": blind_path.name,
        "scientific_status": "NOT_EXECUTED",
    }
    _write_exclusive(
        output_dir / "generation_manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    blind_manifest = {
        "generator_version": GENERATOR_VERSION,
        "status": "BLIND_REVIEW_PACKET",
        "seed": seed,
        "total_cases": len(records),
        "groups": manifest["groups"],
        "blind_review_sha256": manifest["blind_review_sha256"],
        "scientific_status": "NOT_EXECUTED",
    }
    _write_exclusive(
        output_dir / "blind_manifest.json",
        json.dumps(blind_manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    try:
        manifest = generate_package(args.output_dir, seed=args.seed)
    except OSError, ValueError:
        return 1
    print(json.dumps({key: manifest[key] for key in ("status", "total_cases", "groups")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
