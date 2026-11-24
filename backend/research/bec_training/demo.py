"""Casos artificiales para probar la aplicación; no son evidencia científica.

El generador es determinista y compone textos a partir de fragmentos para evitar
duplicados exactos o casi duplicados entre grupos. Aun así, los conteos que
produzca solo demuestran el funcionamiento del software.
"""

import random
from datetime import UTC, datetime, timedelta

from app.schemas.dataset import DatasetLabel, ExpectedBECType
from research.bec_training.data import SEED, ResearchCase

_BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)

_EXECUTIVES = (
    ("Nora Prisma", "nora@luminaria.example"),
    ("Teo Bruma", "teo@luminaria.example"),
    ("Elia Nexo", "elia@luminaria.example"),
    ("Lian Delta", "lian@luminaria.example"),
)

_VENDORS = (
    ("Cobre Azul Ficticio", "cobreazul.example", "facturas@cobreazul.example"),
    ("Papel Nube Ficticio", "papelnube.example", "ventas@papelnube.example"),
    ("Circuito Prisma Ficticio", "circuitoprisma.example", "soporte@circuitoprisma.example"),
    ("Ruta Violeta Ficticia", "rutavioleta.example", "cobros@rutavioleta.example"),
)

_LOOKALIKES = {
    "luminaria.example": ("luminar1a.example", "luminariaa.example", "luminari4.example"),
    "cobreazul.example": ("cobreaazul.example", "cobreazul1.example", "cobrezul.example"),
    "papelnube.example": ("papelnubee.example", "papelnube1.example", "papelnub3.example"),
    "circuitoprisma.example": (
        "circuitoprisma1.example",
        "circuitoprisma2.example",
        "circuitoprisma3.example",
    ),
    "rutavioleta.example": (
        "rutavioletaa.example",
        "rutavioleta1.example",
        "rutaviolet4.example",
    ),
}

_PREFIXES = (
    "Buen día, equipo de finanzas.",
    "Saludos desde la coordinación administrativa.",
    "Escribo desde el área de tesorería externa.",
    "Comparto una actualización breve del expediente.",
    "Retomo el contacto por el proceso de facturación.",
    "Adjunto el resumen operativo de esta semana.",
    "Necesitamos coordinar el cierre del trimestre.",
    "Te contacto por la revisión documental pendiente.",
    "Solicito tu apoyo con la gestión del expediente.",
    "Quedo atento al seguimiento del contrato.",
)

_BANK_REQUESTS = (
    "Por favor, cambia la cuenta bancaria para el pago de la factura {ref}.",
    "Necesitamos reemplazar la cuenta bancaria asociada al pago pendiente {ref}.",
    "Actualiza la cuenta bancaria del pago {ref} antes del cierre contable.",
    "Es necesario sustituir la cuenta bancaria del pago de la factura {ref}.",
    "Confirma el cambio de cuenta bancaria para el pago {ref}.",
    "Gestiona una nueva cuenta bancaria para el pago de la factura {ref}.",
)

_SENSITIVE_REQUESTS = (
    "Necesitamos el maestro completo de nómina para la revisión {ref}.",
    "Solicitamos credenciales del portal para la auditoría {ref}.",
    "Envía los datos individuales del personal antes del cierre {ref}.",
    "Solicito las identificaciones y contrasenas del equipo para el alta {ref}.",
    "Por favor comparte los registros fiscales del personal para la validación {ref}.",
)

_EXEC_REQUESTS = (
    "Soy {exec}. Necesito que prepares una transferencia inmediata para la factura {ref}.",
    "Soy {exec}. Envía las credenciales del portal de nómina para la revisión {ref}.",
    "Habla {exec}. Confirma el pago urgente del proveedor {ref}.",
    "Soy {exec}. Necesitamos los datos individuales del personal para la auditoría {ref}.",
    "Soy {exec}. Prepara una transferencia hoy y evita consultar al equipo por {ref}.",
)

_VENDOR_REQUESTS = (
    "{vendor} actualiza su cuenta bancaria para el pago de la factura {ref}.",
    "Somos {vendor} y necesitamos cambiar la cuenta bancaria del pago {ref}.",
    "{vendor} solicita reemplazar la cuenta bancaria del pago pendiente {ref}.",
    "Desde {vendor} confirmamos el cambio de cuenta bancaria para el pago {ref}.",
)

_CLOSINGS = (
    "Procesarlo hoy mismo evita retrasos en la cadena de pago.",
    "Es urgente; necesitamos avanzar de inmediato.",
    "La dirección solicita cerrar el trámite hoy.",
    "Por indicación de la gerencia, procesar de inmediato.",
    "No consultes al proveedor; es una instrucción directa.",
    "Evita verificar por teléfono y registra el cambio de inmediato.",
    "Te agradezco confirmar la recepción del mensaje.",
    "Quedamos atentos a la confirmación del banco.",
    "El comprobante llegará durante la tarde.",
    "Gracias por la gestión.",
)

_ROUTINE_REQUESTS = (
    "La revisión {ref} conserva las aprobaciones y no modifica datos bancarios.",
    "Confirmamos la recepción del contrato {ref} firmado por ambas partes.",
    "El inventario mensual quedó conciliado sin diferencias pendientes.",
    "Adjuntamos el acta {ref} con las firmas del comité de compras.",
    "La factura {ref} fue registrada correctamente en el expediente.",
    "El equipo de soporte resolvió el ticket {ref} durante la mañana.",
    "Compartimos el calendario de entregas para el próximo trimestre.",
    "La auditoría interna revisó el procedimiento {ref} sin observaciones.",
    "Actualizamos el directorio de contactos internos del área.",
    "El área legal aprobó la cláusula {ref} del contrato marco.",
)

_ROUTINE_CLOSINGS = (
    "Quedamos atentos a cualquier comentario.",
    "Gracias por la coordinación.",
    "Cualquier duda, respondemos por este medio.",
    "Saludos cordiales.",
    "El expediente queda disponible para consulta.",
)

_UNIQUE_NOUNS = (
    "archivo",
    "mobiliario",
    "inventario",
    "calendario",
    "catalogo",
    "bodega",
    "sucursal",
    "manual",
    "carpeta",
    "registro",
    "convenio",
    "anexo",
    "formato",
    "cuadro",
    "tablero",
    "muestra",
    "resumen",
    "informe",
    "cronograma",
    "borrador",
    "expediente",
    "directorio",
    "procedimiento",
    "protocolo",
    "presupuesto",
    "contrato",
    "clausula",
    "acta",
    "bitacora",
    "planilla",
    "recibo",
    "catalogo",
    "margen",
    "volumen",
    "deposito",
    "estante",
    "etiqueta",
    "ficha",
    "tomo",
    "indice",
)
_UNIQUE_PLACES = (
    "Bogota",
    "Lima",
    "Quito",
    "Santiago",
    "Montevideo",
    "Caracas",
    "Panama",
    "Madrid",
    "Lisboa",
    "Sevilla",
    "Valencia",
    "Bilbao",
    "Rosario",
    "Cordoba",
    "La Paz",
    "Asuncion",
    "San Jose",
    "Managua",
    "Tegucigalpa",
    "Brasilia",
)
_UNIQUE_QUALIFIERS = (
    "trimestral",
    "anual",
    "preliminar",
    "definitiva",
    "interna",
    "externa",
    "parcial",
    "completa",
    "ordinaria",
    "extraordinaria",
    "regional",
    "central",
    "provisional",
    "definitivo",
    "mensual",
    "semanal",
    "diaria",
    "nocturna",
    "matutina",
    "vespertina",
)

_AUTH_PASS = "mx.correo.example; spf=pass; dkim=pass; dmarc=pass"
_AUTH_DMARC_FAIL = "mx.correo.example; spf=pass; dkim=pass; dmarc=fail"
_AUTH_SPF_FAIL = "mx.correo.example; spf=fail; dkim=pass; dmarc=pass"


def _lookalike(domain: str, index: int) -> str:
    return _LOOKALIKES[domain][index % len(_LOOKALIKES[domain])]


def _fill(template: str, *, ref: str, exec_name: str = "", vendor: str = "") -> str:
    return template.format(ref=ref, exec=exec_name, vendor=vendor)


def _closing(index: int) -> str:
    return _CLOSINGS[(index * 7) % len(_CLOSINGS)]


def _unique_line(number: int) -> str:
    rng = random.Random(number * 1_000_003 + 17)
    nouns = [rng.choice(_UNIQUE_NOUNS) for _ in range(6)]
    places = [rng.choice(_UNIQUE_PLACES) for _ in range(3)]
    qualifiers = [rng.choice(_UNIQUE_QUALIFIERS) for _ in range(4)]
    return (
        f"Revision {qualifiers[0]} del {nouns[0]} en {places[0]}; "
        f"el {nouns[1]} queda archivado con el folio DEMO-DOC-{number:04d}. "
        f"Control {qualifiers[1]} del {nouns[2]} coordinado desde {places[1]}. "
        f"El {nouns[3]} mantiene la version {qualifiers[2]} del lote {number:04d}. "
        f"La copia del {nouns[4]} se conserva en el repositorio de {places[2]} "
        f"junto al {nouns[5]} y la nota {qualifiers[3]}."
    )


def _case(
    index: int,
    *,
    label: DatasetLabel,
    bec_type: ExpectedBECType | None,
    sender_name: str,
    sender_email: str,
    subject: str,
    body: str,
    hard_negative: bool = False,
    auth: str = _AUTH_PASS,
    reply_to: str | None = None,
    return_path: str | None = None,
    group: str | None = None,
) -> ResearchCase:
    number = index + 1
    rationale = (
        "Caso artificial de demostración; no es evidencia científica. "
        f"Etiqueta simulada para la fila {number:04d}."
    )
    return ResearchCase.model_validate(
        {
            "case_id": f"DEMO-{number:04d}",
            "group_id": group or f"DEMO-G-{number:04d}",
            "source_id": f"DEMO-SRC-{number:04d}",
            "label": label.value,
            "expected_bec_type": bec_type.value if bec_type else None,
            "is_hard_negative": hard_negative,
            "label_rationale": rationale,
            "annotation_status": "ADJUDICATED",
            "email": {
                "message_id": f"<fixture-{number:04d}@research.example>",
                "sender_name": sender_name,
                "sender_email": sender_email,
                "reply_to": reply_to,
                "return_path": return_path,
                "to_recipients": ["finanzas@luminaria.example"],
                "subject": subject,
                "body_text": f"{body} {_unique_line(number)}",
                "authentication_results": auth,
                "received_at": (_BASE_TIME + timedelta(hours=number * 7)).isoformat(),
            },
        }
    )


def _bank_change(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    prefix = _PREFIXES[index % len(_PREFIXES)]
    request = _fill(_BANK_REQUESTS[(index // 3) % len(_BANK_REQUESTS)], ref=ref)
    closing = _closing(index)
    sender = f"tesoreria{number}@proveedor-{number % 17}.example"
    return _case(
        index,
        label=DatasetLabel.BEC,
        bec_type=ExpectedBECType.BANK_ACCOUNT_CHANGE,
        sender_name=f"Tesorería Externa {number}",
        sender_email=sender,
        subject=f"Cambio de cuenta bancaria · factura {ref}",
        body=f"{prefix} {request} {closing}",
        auth=_AUTH_DMARC_FAIL if index % 9 == 4 else _AUTH_PASS,
        reply_to=f"cobros{number}@pago-seguro-{number % 11}.example" if index % 7 == 3 else None,
    )


def _executive_impersonation(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    name, official = _EXECUTIVES[index % len(_EXECUTIVES)]
    domain = official.rsplit("@", 1)[-1]
    prefix = _PREFIXES[(index + 3) % len(_PREFIXES)]
    request = _fill(_EXEC_REQUESTS[(index // 2) % len(_EXEC_REQUESTS)], ref=ref, exec_name=name)
    body = f"{prefix} {request} {_closing(index)}"
    if index % 5 == 2:
        sender = official.replace("@", f"+respaldo{number}@")
    else:
        sender = f"{name.split()[0].lower()}.{number}@{_lookalike(domain, index)}"
    return _case(
        index,
        label=DatasetLabel.BEC,
        bec_type=ExpectedBECType.EXECUTIVE_IMPERSONATION,
        sender_name=name,
        sender_email=sender,
        subject=f"Instrucción urgente de {name} · {ref}",
        body=body,
        auth=_AUTH_DMARC_FAIL if index % 8 == 5 else _AUTH_PASS,
    )


def _vendor_fraud(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    vendor, domain, _contact = _VENDORS[index % len(_VENDORS)]
    prefix = _PREFIXES[(index + 5) % len(_PREFIXES)]
    request = _fill(_VENDOR_REQUESTS[(index // 2) % len(_VENDOR_REQUESTS)], ref=ref, vendor=vendor)
    body = f"{prefix} {request} {_closing(index)}"
    if index % 4 == 1:
        sender = f"facturacion{number}@portal-pagos-{number % 13}.example"
    else:
        sender = f"facturas{number}@{_lookalike(domain, index)}"
    return _case(
        index,
        label=DatasetLabel.BEC,
        bec_type=ExpectedBECType.VENDOR_FRAUD,
        sender_name=f"{vendor} · {number}",
        sender_email=sender,
        subject=f"Actualización de datos de pago · {ref}",
        body=body,
        auth=_AUTH_SPF_FAIL if index % 10 == 6 else _AUTH_PASS,
        reply_to=f"respuesta{number}@cobro-express-{number % 9}.example"
        if index % 6 == 2
        else None,
    )


def _sensitive_request(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    prefix = _PREFIXES[(index + 7) % len(_PREFIXES)]
    request = _fill(_SENSITIVE_REQUESTS[(index // 3) % len(_SENSITIVE_REQUESTS)], ref=ref)
    body = f"{prefix} {request} {_closing(index)}"
    return _case(
        index,
        label=DatasetLabel.BEC,
        bec_type=ExpectedBECType.SENSITIVE_DATA_REQUEST,
        sender_name=f"Auditoría Externa {number}",
        sender_email=f"auditoria{number}@nomina-digital-{number % 19}.example",
        subject=f"Solicitud de información interna · {ref}",
        body=body,
        auth=_AUTH_DMARC_FAIL if index % 7 == 2 else _AUTH_PASS,
        return_path=f"rebotes{number}@lista-{number % 15}.example" if index % 11 == 5 else None,
    )


def _legitimate(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    prefix = _PREFIXES[(index + 2) % len(_PREFIXES)]
    request = _fill(_ROUTINE_REQUESTS[(index // 2) % len(_ROUTINE_REQUESTS)], ref=ref)
    closing = _ROUTINE_CLOSINGS[index % len(_ROUTINE_CLOSINGS)]
    return _case(
        index,
        label=DatasetLabel.LEGITIMATE,
        bec_type=None,
        sender_name=f"Equipo Administrativo {number}",
        sender_email=f"procesos{number}@operaciones-{number % 23}.example",
        subject=f"Seguimiento administrativo · {ref}",
        body=f"{prefix} {request} {closing}",
        auth=_AUTH_PASS,
    )


def _legitimate_context(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    name, contact = _EXECUTIVES[index % len(_EXECUTIVES)]
    vendor, _domain, vendor_contact = _VENDORS[(index + 1) % len(_VENDORS)]
    if index % 2:
        request = _fill(_BANK_REQUESTS[(index // 2) % len(_BANK_REQUESTS)], ref=ref)
        sender_name, sender = vendor, vendor_contact
        body = (
            f"{vendor} confirmó su cuenta bancaria registrada. {request} "
            "La verificación telefónica ya fue registrada por el comité."
        )
    else:
        request = _fill(_ROUTINE_REQUESTS[(index // 3) % len(_ROUTINE_REQUESTS)], ref=ref)
        sender_name, sender = name, contact
        body = f"{_PREFIXES[index % len(_PREFIXES)]} {request} {_ROUTINE_CLOSINGS[index % 5]}"
    group = (
        f"DEMO-G-VENDOR-{_VENDORS[(index + 1) % len(_VENDORS)][1].split('.')[0]}"
        if index % 2
        else f"DEMO-G-EXEC-{_EXECUTIVES[index % len(_EXECUTIVES)][1].split('@')[0]}"
    ).upper()
    return _case(
        index,
        label=DatasetLabel.LEGITIMATE,
        bec_type=None,
        sender_name=sender_name,
        sender_email=sender,
        subject=f"Confirmación operativa · {ref}",
        body=body,
        auth=_AUTH_PASS,
        group=group,
    )


def _hard_negative(index: int) -> ResearchCase:
    number = index + 1
    ref = f"REF-2026-{number:05d}"
    vendor, _domain, contact = _VENDORS[index % len(_VENDORS)]
    request = _fill(_BANK_REQUESTS[(index // 2) % len(_BANK_REQUESTS)], ref=ref, vendor=vendor)
    authority = index % 3 == 0
    auth = _AUTH_DMARC_FAIL if index % 3 == 1 else _AUTH_PASS
    closing = (
        "La dirección aprobó el cambio y solicita procesarlo con el procedimiento habitual."
        if authority
        else "El comité de compras validó la solicitud antes del envío."
    )
    body = f"{vendor} gestiona una actualización verificada. {request} {closing}"
    return _case(
        index,
        label=DatasetLabel.LEGITIMATE,
        bec_type=None,
        sender_name=f"{vendor} · Contacto Registrado",
        sender_email=contact,
        subject=f"Actualización verificada de datos · {ref}",
        body=body,
        hard_negative=True,
        auth=auth,
        group=f"DEMO-G-VENDOR-{_VENDORS[index % len(_VENDORS)][1].split('.')[0]}".upper(),
    )


def demo_cases() -> list[ResearchCase]:
    """Devuelve 300 casos sintéticos con los cuatro tipos BEC y negativos difíciles."""
    rng = random.Random(SEED)
    builders = (
        _bank_change,
        _executive_impersonation,
        _vendor_fraud,
        _sensitive_request,
    )
    cases: list[ResearchCase] = []
    for category, builder in enumerate(builders):
        for offset in range(30):
            cases.append(builder(category * 30 + offset))
    for index in range(110):
        cases.append(_legitimate(120 + index))
    for index in range(40):
        cases.append(_legitimate_context(230 + index))
    for index in range(30):
        cases.append(_hard_negative(270 + index))
    rng.shuffle(cases)
    return cases
