"""Revisión ciega de UN evaluador para categorizar phishing sintético como BEC."""

import hashlib
import json
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.dataset import ExpectedBECType  # noqa: E402
from research.bec_training import triage_rules  # noqa: E402
from research.bec_training.single_review import (  # noqa: E402
    Decision,
    load_decisions,
    load_packet,
    save_decision,
)
from research.bec_training.triage_rules import suggest  # noqa: E402

st.set_page_config(page_title="Etiquetado BEC · un evaluador", page_icon=":material/rule:")
for name in (
    "packet",
    "packet_sha",
    "order",
    "directory",
    "reviewer",
    "triage",
    "triage_hash",
    "weak",
    "weak_hash",
):
    if name not in st.session_state:
        st.session_state[name] = None

st.title("Etiquetado ciego BEC sintético", icon=":material/rule:")
st.caption(
    "Un evaluador · solo correos phishing del corpus externo · sin predicciones del modelo. "
    "Los legítimos conservan la etiqueta publicada por el autor."
)
with st.expander("Rúbrica predefinida", icon=":material/menu_book:"):
    st.markdown(
        "**BEC (definición operativa de este estudio):** comunicación empresarial que "
        "suplanta autoridad o proveedor, "
        "o pretende provenir de una cuenta de trabajo comprometida, para solicitar "
        "pagos, cambio de cuenta, información sensible o una acción de negocio "
        "en beneficio del atacante. La urgencia sola no basta. "
        "**Otro phishing (no BEC):** robo de credenciales, alertas de redes sociales, "
        "impuestos o estafas sin ese contexto empresarial. "
        "**No se puede determinar:** el texto no permite distinguirlo; "
        "se excluye del estudio."
    )
with st.expander("Fundamento científico y oficial de la rúbrica", icon=":material/school:"):
    st.markdown(
        "- [FBI/IC3 (2024)](https://www.ic3.gov/PSA/2024/PSA240911): "
        "transferencias fraudulentas y solicitud de datos de empleados. "
        "[FBI/IC3 (2023)](https://www.ic3.gov/PSA/2023/PSA230609): "
        "cambios bancarios y billeteras cripto también pueden intervenir en BEC.\n"
        "- [Cidon et al., USENIX Security (2019)]"
        "(https://www.usenix.org/conference/usenixsecurity19/presentation/cidon): "
        "texto, identidad y relaciones de correo se combinan; una palabra sola no prueba BEC.\n"
        "- [Ho et al., USENIX Security (2019)]"
        "(https://www.usenix.org/conference/usenixsecurity19/presentation/ho): "
        "una cuenta empresarial comprometida puede enviar phishing lateral.\n"
        "- [CISA, guía de phishing]"
        "(https://www.cisa.gov/secure-our-world/recognize-and-report-phishing): "
        "URL, credenciales y urgencia son señales generales de phishing, no BEC por sí solas.\n"
        "- [Ratner et al., PVLDB (2017)]"
        "(https://doi.org/10.14778/3157794.3157797): "
        "las reglas de etiquetado pueden tener precisión desconocida; aquí solo priorizan."
    )
    st.caption(
        "Matriz completa, límites y fuentes: docs/research/FUNDAMENTO_RUBRICA_BEC.md. "
        "Estos estudios justifican señales y cautela, no la precisión de nuestra regla."
    )
with st.expander("Ayuda para leer el correo en inglés", icon=":material/translate:"):
    st.markdown(
        "**wire transfer** = transferencia bancaria · **bank account details** = datos de cuenta · "
        "**invoice** = factura · **CEO/CFO** = director general/financiero · "
        "**confidential** = confidencial · **do not call** = no llames · "
        "**verify your identity** = verifica tu identidad (esto solo NO implica BEC). "
        "En Edge/Chrome: clic derecho → «Traducir al español» como apoyo; si la traducción "
        "hace ambiguo el mensaje, elige «No se puede determinar»."
    )

default_dir = os.environ.get(
    "BEC_SINGLE_REVIEW_DIR",
    str(Path(__file__).resolve().parents[2] / "artifacts" / "research" / "bec_single_v3"),
)
chosen = st.text_input("Directorio local del paquete", value=default_dir, key="review_dir")
reviewer = "ADRIAN"
st.caption("Identificador del único evaluador: ADRIAN · se guarda sin correo personal")


def open_packet() -> None:
    directory = Path(chosen)
    manifest = json.loads((directory / "selection_manifest.json").read_text(encoding="utf-8"))
    cases, digest = load_packet(directory / "blind_packet.jsonl")
    if (
        manifest.get("status") != "SINGLE_ANNOTATOR_SYNTHETIC_PENDING"
        or manifest.get("packet_sha256") != digest
    ):
        raise ValueError("Selection and review packet do not match")
    triage_path = directory / "triage_manifest.json"
    triage = None
    triage_hash = None
    if triage_path.is_file():
        triage_bytes = triage_path.read_bytes()
        triage = json.loads(triage_bytes)
        triage_hash = hashlib.sha256(triage_bytes).hexdigest()
        if (
            triage.get("status") != "TRIAGE_REVIEW_PENDING"
            or triage.get("packet_sha256") != digest
            or not set(triage.get("review_required", [])) <= {row["case_id"] for row in cases}
        ):
            raise ValueError("Triage review list differs from the blind packet")
    weak_path = directory / "weak_train_manifest.json"
    weak = None
    weak_hash = None
    if weak_path.is_file():
        if triage is None:
            raise ValueError("Weak-training cohort needs its triage allocation")
        weak_bytes = weak_path.read_bytes()
        weak = json.loads(weak_bytes)
        weak_hash = hashlib.sha256(weak_bytes).hexdigest()
        evaluation = set(
            triage["publisher_splits"]["validation"] + triage["publisher_splits"]["test"]
        )
        if (
            weak.get("status") != "WEAK_TRAIN_HUMAN_EVAL_PENDING"
            or weak.get("packet_sha256") != digest
            or weak.get("triage_manifest_sha256") != triage_hash
            or not set(weak.get("review_required", [])) <= evaluation
        ):
            raise ValueError("Weak-training review list differs from the sealed evaluation")
    Decision(
        reviewer_id=reviewer,
        packet_sha256=digest,
        case_id=cases[0]["case_id"],
        content_sha256=cases[0]["content_sha256"],
        label="OTHER_PHISHING",
        rationale="ID válido",
        reviewed_at=datetime.now(UTC),
    )
    st.session_state["packet"] = {row["case_id"]: row for row in cases}
    st.session_state["packet_sha"] = digest
    case_ids = (
        weak["review_required"]
        if weak
        else (triage["review_required"] if triage else [row["case_id"] for row in cases])
    )
    st.session_state["order"] = random.Random(f"{digest}:{reviewer}").sample(
        case_ids, len(case_ids)
    )
    st.session_state["directory"] = directory
    st.session_state["reviewer"] = reviewer
    st.session_state["triage"] = triage
    st.session_state["triage_hash"] = triage_hash
    st.session_state["weak"] = weak
    st.session_state["weak_hash"] = weak_hash
    st.success(f"Paquete listo: {len(case_ids)} casos para revisión, sin etiquetas visibles.")


triage_path = Path(chosen) / "triage_manifest.json"
triage_hash_on_disk = (
    hashlib.sha256(triage_path.read_bytes()).hexdigest() if triage_path.is_file() else None
)
weak_path = Path(chosen) / "weak_train_manifest.json"
weak_hash_on_disk = (
    hashlib.sha256(weak_path.read_bytes()).hexdigest() if weak_path.is_file() else None
)
if (
    Path(chosen) == Path(default_dir)
    and (Path(default_dir) / "blind_packet.jsonl").is_file()
    and (
        st.session_state["packet"] is None
        or st.session_state["triage_hash"] != triage_hash_on_disk
        or st.session_state["weak_hash"] != weak_hash_on_disk
    )
):
    try:
        open_packet()
    except OSError, ValueError, KeyError, IndexError:
        st.error("No se pudo verificar el paquete local.")

if st.button("Abrir paquete ciego", type="primary", key="load_packet"):
    try:
        open_packet()
    except OSError, ValueError, KeyError, IndexError:
        st.error("No se pudo verificar el paquete. Comprueba el directorio local.")

packet = st.session_state["packet"]
if not packet:
    st.info("Primero genera el paquete con `single_review prepare` y ábrelo aquí.")
    st.stop()

directory = st.session_state["directory"]
digest = st.session_state["packet_sha"]
try:
    decisions = load_decisions(directory / "single_annotations.jsonl", packet_sha256=digest)
    if decisions and next(iter(decisions.values())).reviewer_id != st.session_state["reviewer"]:
        raise ValueError("A second reviewer cannot be mixed into this file")
except ValueError, OSError:
    st.error("Las anotaciones locales no coinciden con el paquete cargado.")
    st.stop()

order = st.session_state["order"]
pending = [case_id for case_id in order if case_id not in decisions]
completed = len(order) - len(pending)
st.progress(completed / len(order), text=f"{completed} de {len(order)} revisados")
triage = st.session_state["triage"]
weak = st.session_state["weak"]
if weak:
    st.caption(
        "BEC de entrenamiento: borradores automáticos con fuente identificada, "
        "no decisiones de ADRIAN. Aquí solo se revisan los phishing de "
        "validación y test, sin mostrar sus borradores automáticos."
    )
elif triage:
    st.caption(
        "La regla solo priorizó los casos del entrenamiento: los claros descartados "
        "se excluyen, nunca se guardan como decisiones de ADRIAN. Todos los casos "
        "de validación y test requieren lectura humana."
    )
if not pending:
    next_command = (
        "weak_supervision freeze"
        if weak
        else ("triage_workflow freeze" if triage else "single_review freeze")
    )
    st.success(f"Revisión completa. Ejecuta `{next_command}` desde la terminal.")
    st.stop()

case = packet[pending[0]]
st.caption(f"Caso {case['case_id']} · quedan {len(pending)} · sin score del modelo")
if triage and case["case_id"] in triage["publisher_splits"]["train"]:
    draft = suggest(case["subject"], case["body"])
    st.info(f"Filtro automático (no es una etiqueta): {draft.reason_es}")
    text = f"{case['subject']}\n{case['body']}"
    matched = [
        f"{name}: «{match.group(0)}»"
        for name, pattern in (
            ("Solicitud financiera", triage_rules._FINANCE),
            ("Contexto empresarial", triage_rules._BUSINESS),
            ("Acción solicitada", triage_rules._ACTION),
            ("Verificación de cuenta", triage_rules._ACCOUNT_PHISHING),
            ("Tema de consumo", triage_rules._CONSUMER),
        )
        if (match := pattern.search(text)) is not None
    ]
    st.caption(
        "Coincidencias del filtro: "
        + (" · ".join(matched) if matched else "ninguna")
        + ". Son indicios para revisar, no una clasificación confirmada."
    )
st.caption(
    "El correo original del dataset está en inglés. La rúbrica y las opciones están "
    "en español; si una traducción cambia el sentido, elige «No se puede determinar»."
)
st.subheader(case["subject"] or "(sin asunto)")
st.text(case["body"])

visible_labels = {
    "Seleccionar": None,
    "BEC · fraude empresarial": "BEC",
    "Otro phishing (no BEC)": "OTHER_PHISHING",
    "No se puede determinar": "UNCERTAIN",
}
visible_choice = st.radio(
    "Categoría según la rúbrica",
    list(visible_labels),
    key=f"label_{case['case_id']}",
)
choice = visible_labels[visible_choice]
bec_type = None
if choice == "BEC":
    visible_types = {
        "Suplantación de directivo": ExpectedBECType.EXECUTIVE_IMPERSONATION,
        "Fraude de proveedor": ExpectedBECType.VENDOR_FRAUD,
        "Cambio de cuenta bancaria": ExpectedBECType.BANK_ACCOUNT_CHANGE,
        "Solicitud de datos sensibles": ExpectedBECType.SENSITIVE_DATA_REQUEST,
        "Otro tipo BEC": ExpectedBECType.OTHER,
    }
    selected_type = st.selectbox(
        "Subtipo BEC",
        ["Seleccionar", *visible_types],
        key=f"type_{case['case_id']}",
    )
    bec_type = visible_types.get(selected_type)
rationale = st.text_area(
    "Justificación breve (qué observaste, sin consultar el modelo)",
    key=f"rationale_{case['case_id']}",
    max_chars=500,
)
if st.button(
    "Guardar y siguiente",
    type="primary",
    key="save_review",
    disabled=choice is None or (choice == "BEC" and bec_type is None) or len(rationale.strip()) < 4,
):
    try:
        decision = Decision(
            reviewer_id=st.session_state["reviewer"],
            packet_sha256=digest,
            case_id=case["case_id"],
            content_sha256=case["content_sha256"],
            label=cast(Literal["BEC", "OTHER_PHISHING", "UNCERTAIN"], choice),
            bec_type=bec_type,
            rationale=rationale.strip(),
            reviewed_at=datetime.now(UTC),
        )
        save_decision(directory, decision)
        st.rerun()
    except ValueError, OSError:
        st.error("No se pudo guardar: verifica el paquete y el directorio privado.")
