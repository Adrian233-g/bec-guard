"""Interfaz local para resolver desacuerdos y exportar el corpus adjudicado."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.dataset import DatasetLabel, ExpectedBECType  # noqa: E402
from research.bec_training.annotation import (  # noqa: E402
    ReviewAnnotation,
    build_adjudicated_cases,
    compare_reviewers,
    load_annotations_bytes,
    load_blind_packet_bytes,
)
from research.bec_training.data import ResearchDataError  # noqa: E402

st.set_page_config(page_title="Adjudicación BEC Guard", page_icon=":material/gavel:")
st.title("Adjudicación de anotaciones")
st.caption("Solo se muestran casos con desacuerdo; las etiquetas generadas no se cargan.")

packet_file = st.file_uploader("Paquete blind_review.jsonl", type=["jsonl"])
left_file, right_file = st.columns(2)
with left_file:
    reviewer_a = st.text_input("ID revisor A", value="REVIEWER_A")
    annotations_a = st.file_uploader("Anotaciones A", type=["jsonl"], key="annotations_a")
with right_file:
    reviewer_b = st.text_input("ID revisor B", value="REVIEWER_B")
    annotations_b = st.file_uploader("Anotaciones B", type=["jsonl"], key="annotations_b")

if st.button(
    "Cargar revisiones",
    type="primary",
    disabled=packet_file is None or annotations_a is None or annotations_b is None,
):
    if packet_file is None or annotations_a is None or annotations_b is None:
        st.error("Seleccione el paquete y las dos revisiones.")
        st.stop()
    try:
        cases, packet_hash = load_blind_packet_bytes(packet_file.getvalue())
        first = load_annotations_bytes(
            annotations_a.getvalue(), reviewer_id=reviewer_a, packet_hash=packet_hash
        )
        second = load_annotations_bytes(
            annotations_b.getvalue(), reviewer_id=reviewer_b, packet_hash=packet_hash
        )
        summary = compare_reviewers(cases, first, second, packet_hash=packet_hash)
        st.session_state["adjudication"] = {
            "cases": {case.case_id: case for case in cases},
            "packet_hash": packet_hash,
            "first": first,
            "second": second,
            "summary": summary,
        }
    except ResearchDataError:
        st.error("No se pudieron cargar las revisiones. Compruebe IDs, completitud y hash.")

state = st.session_state.get("adjudication")
if not state:
    st.info("Cargue el paquete y las dos revisiones para continuar.")
    st.stop()

summary = state["summary"]
if summary["status"] != "READY_FOR_ADJUDICATION":
    st.warning("Ambos revisores deben completar todos los casos antes de adjudicar.")
    st.stop()

decisions = {}
for case_id in summary["disagreements"]:
    case = state["cases"][case_id]
    first = state["first"][case_id]
    second = state["second"][case_id]
    with st.container(border=True):
        st.subheader(case_id)
        st.caption(case.email.subject or "(sin asunto)")
        st.write(case.email.body_text)
        st.caption(
            f"Remitente: {case.email.sender_name or '(sin nombre)'} <{case.email.sender_email}>"
        )
        st.write(f"Revisor A: **{first.label.value}** · {first.expected_bec_type or 'sin tipo'}")
        st.write(f"Revisor B: **{second.label.value}** · {second.expected_bec_type or 'sin tipo'}")
        final_label = st.radio(
            "Decisión del árbitro",
            [item.value for item in DatasetLabel],
            key=f"label_{case_id}",
        )
        final_type = None
        final_hard_negative = False
        if final_label == DatasetLabel.BEC.value:
            final_type_text = st.selectbox(
                "Tipo BEC adjudicado",
                [item.value for item in ExpectedBECType],
                key=f"type_{case_id}",
            )
            final_type = ExpectedBECType(final_type_text)
        else:
            final_hard_negative = st.checkbox("Negativo difícil", key=f"hard_{case_id}")
        rationale = st.text_area("Justificación del árbitro", key=f"reason_{case_id}")
        if rationale.strip():
            decisions[case_id] = ReviewAnnotation(
                reviewer_id="ADJUDICATOR",
                packet_sha256=state["packet_hash"],
                case_id=case_id,
                label=DatasetLabel(final_label),
                expected_bec_type=final_type,
                is_hard_negative=final_hard_negative,
                rationale=rationale.strip(),
                reviewed_at=datetime.now(UTC),
            )

if st.button(
    "Generar corpus adjudicado",
    type="primary",
    disabled=len(decisions) != len(summary["disagreements"]),
):
    try:
        records = build_adjudicated_cases(
            list(state["cases"].values()),
            state["first"],
            state["second"],
            decisions,
            packet_hash=state["packet_hash"],
        )
        content = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
        )
        st.download_button(
            "Descargar corpus adjudicado",
            content,
            file_name="bec-synthetic-v1-adjudicated.jsonl",
            mime="application/jsonl",
            type="primary",
        )
    except ResearchDataError:
        st.error("No se pudo construir el corpus adjudicado.")
