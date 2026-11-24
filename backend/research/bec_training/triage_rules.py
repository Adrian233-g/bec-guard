"""Sugerencias NO etiquetadas para priorizar una revisión humana BEC sintética."""

import re
from typing import NamedTuple

RULE_VERSION = "triage-text-v2"

_FINANCE = re.compile(
    r"\b(?:wire transfer|bank account|routing number|beneficiary|invoice|"
    r"accounts payable|payroll|payment instructions|outgoing wire|legal retainer)\b",
    re.I,
)
_BUSINESS = re.compile(
    r"\b(?:ceo|cfo|chief executive|director|vendor|supplier|company|"
    r"board meeting|finance team|legal representative|corporate|acquisition|attorneys)\b",
    re.I,
)
_ACTION = re.compile(
    r"\b(?:process|initiate|authorize|send|transfer|change|update|pay|settle|approve)\b",
    re.I,
)
_ACCOUNT_PHISHING = re.compile(
    r"\b(?:verify your identity|confirm your identity|secure your account|"
    r"login attempt|password reset|account compromised|account suspended|"
    r"account will be locked|kyc|update your details|verify your account)\b",
    re.I,
)
_CONSUMER = re.compile(
    r"\b(?:gift card|claim your prize|package delivery|shipping information|"
    r"irs|social media|discord|twitter|amazon order)\b",
    re.I,
)


class Triage(NamedTuple):
    bucket: str
    reason_es: str


def suggest(subject: str, body: str) -> Triage:
    """No genera verdad de terreno; solo decide qué casos de train se priorizan."""
    text = f"{subject}\n{body}"
    if _FINANCE.search(text) and _BUSINESS.search(text) and _ACTION.search(text):
        return Triage(
            "POSIBLE_BEC",
            "Hay solicitud financiera y señales de contexto empresarial; verifica quién pide qué.",
        )
    if _CONSUMER.search(text) and not _BUSINESS.search(text):
        return Triage(
            "OTRO_CLARO",
            "Parece estafa de consumo, redes, entrega o premio; comprueba si hay contexto BEC.",
        )
    if _ACCOUNT_PHISHING.search(text) and not _BUSINESS.search(text) and not _FINANCE.search(text):
        return Triage(
            "OTRO_CLARO",
            "Pide verificar una cuenta o identidad; no se ve una solicitud empresarial BEC.",
        )
    return Triage(
        "DUDOSO",
        "El texto no permite descartarlo por regla; lee el mensaje completo y aplica la rúbrica.",
    )
