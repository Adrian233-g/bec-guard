"""Interfaz local para dos revisiones ciegas independientes."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.dataset import DatasetLabel, ExpectedBECType  # noqa: E402
from research.bec_training.annotation import (  # noqa: E402
    ReviewAnnotation,
    load_annotations,
    load_blind_packet_bytes,
    review_order,
    reviewer_path,
    save_annotation,
)
from research.bec_training.data import ResearchDataError  # noqa: E402

st.set_page_config(page_title="Revisión ciega BEC Guard", page_icon=":material/rule:")

for name, default in (("packet", None), ("packet_hash", None), ("cases", None), ("order", None)):
    if name not in st.session_state:
        st.session_state[name] = default

st.title("Revisión ciega de correos")

reviewer_id = st.text_input(
    "ID del revisor",
    value="REVIEWER_A",
    help="Use IDs distintos, por ejemplo REVIEWER_A y REVIEWER_B.",
)
output_dir = st.text_input(
    "Directorio privado de anotaciones",
    value=os.environ.get(
        "BEC_RESEARCH_ANNOTATION_DIR",
        str(Path(__file__).resolve().parents[2] / "artifacts" / "research" / "annotations"),
    ),
)
uploaded = st.file_uploader("Paquete blind_review.jsonl", type=["jsonl"])

if st.button("Cargar paquete", type="primary", disabled=uploaded is None):
    if uploaded is None:
        st.error("Seleccione un paquete ciego.")
        st.stop()
    try:
        contents = uploaded.getvalue()
        cases, digest = load_blind_packet_bytes(contents)
        st.session_state["packet"] = contents
        st.session_state["packet_hash"] = digest
        st.session_state["cases"] = {case.case_id: case for case in cases}
        st.session_state["order"] = review_order(cases, reviewer_id=reviewer_id, packet_hash=digest)
        st.success(f"Paquete cargado: {len(cases)} casos. Hash {digest[:12]}…")
    except ResearchDataError:
        st.error("No se pudo cargar el paquete ciego.")

cases = st.session_state["cases"]
packet_hash = st.session_state["packet_hash"]
order = st.session_state["order"]
if not cases or not packet_hash or not order:
    st.info("Cargue el paquete ciego para comenzar.")
    st.stop()

try:
    path = reviewer_path(Path(output_dir), reviewer_id)
    annotations = load_annotations(path, reviewer_id=reviewer_id, packet_hash=packet_hash)
except ResearchDataError:
    st.error("El ID o el archivo de anotaciones no son válidos.")
    st.stop()

pending = [case_id for case_id in order if case_id not in annotations]
st.progress(len(annotations) / len(order), text=f"{len(annotations)} de {len(order)} revisados")
if not pending:
    st.success("Este revisor completó todos los casos. No se muestran etiquetas de referencia.")
    st.stop()

case_id = pending[0]
case = cases[case_id]
st.caption(f"Caso {case_id} · quedan {len(pending)}")
st.subheader(case.email.subject or "(sin asunto)")
st.write(case.email.body_text)
st.caption(
    f"Remitente mostrado: {case.email.sender_name or '(sin nombre)'} <{case.email.sender_email}>"
)

label_text = st.radio("Clasificación", ["Seleccionar", "LEGITIMATE", "BEC"], index=0)
label = None if label_text == "Seleccionar" else DatasetLabel(label_text)
bec_type = None
hard_negative = False
if label == DatasetLabel.BEC:
    bec_type_text = st.selectbox(
        "Tipo BEC", ["Seleccionar"] + [item.value for item in ExpectedBECType]
    )
    bec_type = None if bec_type_text == "Seleccionar" else ExpectedBECType(bec_type_text)
elif label == DatasetLabel.LEGITIMATE:
    hard_negative = st.checkbox("Negativo difícil", value=False)
rationale = st.text_area("Justificación breve", max_chars=1000)

if st.button(
    "Guardar anotación",
    type="primary",
    disabled=label is None
    or (label == DatasetLabel.BEC and bec_type is None)
    or not rationale.strip(),
):
    annotation = ReviewAnnotation(
        reviewer_id=reviewer_id,
        packet_sha256=packet_hash,
        case_id=case_id,
        label=label,
        expected_bec_type=bec_type,
        is_hard_negative=hard_negative,
        rationale=rationale.strip(),
        reviewed_at=datetime.now(UTC),
    )
    save_annotation(path, annotation)
    st.rerun()
