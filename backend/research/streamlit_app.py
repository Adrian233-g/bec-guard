"""Laboratorio local de BEC Guard. Entrada autorizada en memoria; sin llamadas a API."""

import hashlib
import io
import json
import os
import sys
from pathlib import Path

import streamlit as st

# Streamlit ejecuta el script desde research/; app y research viven bajo backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.bec_training.data import (  # noqa: E402
    CorpusUse,
    ResearchDataError,
    load_research_bytes,
    split_manifest,
)
from research.bec_training.demo import demo_cases  # noqa: E402
from research.bec_training.experiments import compare_offline  # noqa: E402
from research.bec_training.inputs import (  # noqa: E402
    EMPTY_CONTEXT_SHA256,
    load_context_bytes,
    load_semantic_cache,
)
from research.bec_training.public_reports import AUX, summarize_public_report  # noqa: E402
from research.bec_training.reporting import summarize_experiment  # noqa: E402
from research.bec_training.statistics import technical_statistics  # noqa: E402
from research.bec_training.training import train_offline  # noqa: E402

st.set_page_config(
    page_title="Laboratorio BEC Guard", page_icon=":material/science:", layout="wide"
)
for name in (
    "cases",
    "manifest",
    "training",
    "training_model_bytes",
    "comparison",
    "comparison_raw",
    "context",
    "use",
):
    if name not in st.session_state:
        st.session_state[name] = None
if "final_test_hashes" not in st.session_state:
    st.session_state["final_test_hashes"] = set()


def final_test_lock_dir() -> Path:
    configured = os.environ.get("BEC_RESEARCH_TEST_LOCK_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "artifacts" / "research" / "test-locks"


def go_to_data() -> None:
    st.session_state["vista"] = "Datos"


cases = st.session_state["cases"]
manifest = st.session_state["manifest"]
use = st.session_state["use"]
with st.sidebar:
    st.markdown("### :material/shield: BEC Guard")
    st.caption("LABORATORIO · INVESTIGACIÓN")
    st.space("small")
    section = st.radio(
        "Secciones",
        [
            "Resumen",
            "Metodología",
            "Datos",
            "Entrenamiento",
            "Comparación",
            "Estadística",
            "Transferencia",
            "Informe",
        ],
        key="vista",
        label_visibility="collapsed",
    )
    st.space("medium")
    st.caption("AVANCE DEL EXPERIMENTO")
    completed = sum(
        value is not None
        for value in (cases, st.session_state["training"], st.session_state["comparison"])
    )
    st.progress(completed / 3, text=f"{completed} de 3 pasos preparados")
    if use and use.kind == "authorized":
        st.badge("Corpus autorizado declarado", color="blue", icon=":material/verified_user:")
    elif cases:
        st.badge("Fixture artificial", color="orange", icon=":material/science:")
    else:
        st.badge("Sin datos cargados", color="gray", icon=":material/pending:")
    st.caption("Local · sin envíos a proveedores")

st.caption("BEC GUARD  /  LABORATORIO EXPERIMENTAL")
st.title("Centro de investigación", icon=":material/shield:")
st.caption("Entrena, compara y documenta el análisis de fraude por correo en un entorno aislado.")
if use and use.kind == "authorized":
    st.badge("Uso declarado: autorizado", color="blue", icon=":material/lock:")
else:
    st.badge(
        "Modo demostración · resultados no científicos", color="orange", icon=":material/info:"
    )

if section == "Resumen":
    st.header("Tu espacio de trabajo", icon=":material/dashboard:")
    st.markdown("Un recorrido controlado, desde el corpus hasta un informe reproducible.")
    dataset_card, model_card, comparison_card = st.columns(3, border=True)
    with dataset_card:
        st.caption("01 / CORPUS")
        st.metric("Casos cargados", len(cases) if cases else "—")
        st.caption("Validación de etiquetas, duplicados y particiones por grupos.")
    with model_card:
        st.caption("02 / ENTRENAMIENTO")
        st.metric("Búsqueda", "Lista" if st.session_state["training"] else "Pendiente")
        st.caption("TF-IDF, regresión logística y 3 folds sin fuga entre grupos.")
    with comparison_card:
        st.caption("03 / COMPARACIÓN")
        st.metric("Condiciones", "C1–C7" if st.session_state["comparison"] else "Pendiente")
        st.caption("Reglas, ablaciones, cobertura y alertas en el mismo conjunto.")
    st.space("small")
    with st.container(border=True):
        st.subheader("Empieza con un caso controlado", icon=":material/play_circle:")
        st.markdown(
            "Carga los mensajes ficticios incorporados para conocer el flujo sin preparar archivos "
            "ni conectar servicios externos."
        )
        st.button(
            "Ir a datos",
            icon=":material/arrow_forward:",
            type="primary",
            key="start_demo",
            on_click=go_to_data,
        )
    st.caption(
        "Los fixtures comprueban el software; los resultados científicos requieren un corpus "
        "nuevo, etiquetado y autorizado."
    )

elif section == "Metodología":
    st.header("Metodología del laboratorio", icon=":material/menu_book:")
    st.caption(
        "Qué identifica el motor, cómo combina señales y qué conclusiones permite este diseño."
    )
    st.subheader("Qué ayuda a detectar", icon=":material/flag:")
    st.markdown(
        "BEC Guard prioriza el **Business Email Compromise**: mensajes que suplantan identidad "
        "o proveedores para mover dinero o extraer información. No emite un veredicto "
        "automático: produce riesgo y alertas para revisión humana."
    )
    type_rows = [
        {
            "tipo": "EXECUTIVE_IMPERSONATION",
            "qué busca": "Directivo suplantado con otro dominio o dirección.",
            "señales": "Nombre registrado, dominio similar, solicitud accionable.",
        },
        {
            "tipo": "VENDOR_FRAUD",
            "qué busca": "Proveedor falso o contacto alterado.",
            "señales": "Dominio parecido, contacto distinto al registrado.",
        },
        {
            "tipo": "BANK_ACCOUNT_CHANGE",
            "qué busca": "Cambio de cuenta bancaria o beneficiario.",
            "señales": "Solicitud de nueva cuenta, pago, urgencia, secreto.",
        },
        {
            "tipo": "SENSITIVE_DATA_REQUEST",
            "qué busca": "Extracción de nómina, credenciales o datos personales.",
            "señales": "Verbos de solicitud, datos sensibles, presión de tiempo.",
        },
    ]
    st.dataframe(type_rows, hide_index=True, alt="Tipos de BEC y señales que busca el motor")

    st.subheader("Cómo trabaja el motor", icon=":material/account_tree:")
    step_signals, step_rules, step_semantic, step_hybrid, step_alert = st.columns(5)
    with step_signals:
        with st.container(border=True):
            st.caption("01 · ENTRADA")
            st.markdown("**Señales objetivas**")
            st.caption("Cabeceras, remitente, Reply-To, SPF/DKIM/DMARC y contexto activo.")
    with step_rules:
        with st.container(border=True):
            st.caption("02 · REGLAS")
            st.markdown("**det-v3**")
            st.caption("Suma ponderada de evidencia; score 0–100 ordinal, no probabilidad.")
    with step_semantic:
        with st.container(border=True):
            st.caption("03 · SEMÁNTICA")
            st.markdown("**semantic-v2**")
            st.caption("Lectura estructurada del texto; solo con proveedor autorizado o cache.")
    with step_hybrid:
        with st.container(border=True):
            st.caption("04 · HÍBRIDO")
            st.markdown("**hybrid-v2**")
            st.caption("Promedio entero y pisos 50/70 cuando hay evidencia fuerte de identidad.")
    with step_alert:
        with st.container(border=True):
            st.caption("05 · ALERTA")
            st.markdown("**alert-v2**")
            st.caption("Alerta operativa desde 50; 40 marca detección, no alerta.")
    band_rows = [
        {"rango": "0–39", "lectura": "Sin señal relevante"},
        {"rango": "40–49", "lectura": "Detección: revisar, no alertar (política actual)"},
        {"rango": "50–69", "lectura": "Alerta operativa"},
        {"rango": "70–84", "lectura": "Riesgo alto; pisos por suplantación"},
        {"rango": "85–100", "lectura": "Riesgo crítico"},
    ]
    st.dataframe(band_rows, hide_index=True, alt="Bandas de riesgo y lectura operativa")
    st.caption(
        "Un score alto no es una probabilidad calibrada ni una prueba de fraude: es evidencia "
        "ordinal para priorizar la revisión humana."
    )

    st.subheader("Condiciones experimentales", icon=":material/science:")
    condition_rows = [
        {
            "condición": "C1",
            "usa": "Reglas + contexto",
            "mide": "Aporte del motor determinista vigente.",
        },
        {
            "condición": "C2",
            "usa": "Solo semántica",
            "mide": "Lectura del LLM sin señales locales.",
        },
        {
            "condición": "C3",
            "usa": "Híbrido",
            "mide": "Combinación principal con pisos de identidad.",
        },
        {
            "condición": "C4",
            "usa": "Reglas sin contexto",
            "mide": "Efecto de ejecutivos, proveedores y verificaciones.",
        },
        {
            "condición": "C5",
            "usa": "Promedio plano",
            "mide": "Diferencia frente a pisos y redondeo del híbrido.",
        },
        {
            "condición": "C6",
            "usa": "Híbrido con umbral 70",
            "mide": "Costo de una política más conservadora.",
        },
        {
            "condición": "C7",
            "usa": "Fallback por caída",
            "mide": "Cobertura cuando el proveedor no responde.",
        },
    ]
    st.dataframe(condition_rows, hide_index=True, alt="Condiciones C1 a C7 del experimento")

    st.subheader("Estadística y control metodológico", icon=":material/query_stats:")
    metrics_col, design_col = st.columns(2, gap="large")
    with metrics_col:
        st.markdown(
            "- Matriz de confusión en **detección (40)** y **alerta (50)**.\n"
            "- Recall, FPR, precisión, F1 y recall efectivo con denominadores explícitos.\n"
            "- **Average precision** y ROC-AUC solo con scores completos y comparables.\n"
            "- **Wilson 95 %** para recall, FPR y especificidad.\n"
            "- **Bootstrap por grupos** (2000 réplicas) para diferencias C3 vs C1/C2.\n"
            "- **McNemar exacto** con ≥10 discordancias y **Holm** para dos contrastes "
            "preespecificados."
        )
    with design_col:
        st.markdown(
            "- Partición **70/15/15 por grupos**; un corpus de evaluación independiente no "
            "se fragmenta.\n"
            "- CV agrupada de 3 folds solo en train; validation elige umbral; test se congela "
            "y se evalúa una vez.\n"
            "- Errores y fallos del LLM son **falta de cobertura**, nunca verdaderos negativos.\n"
            "- Fixtures y scores hipotéticos se etiquetan como demostración técnica.\n"
            "- Sin llamadas externas, sin base operativa y sin contenido de correos en reportes."
        )
    with st.expander("Qué no hace ni permite concluir", icon=":material/warning:"):
        st.markdown(
            "No entrena al LLM, no modifica producción, no acusa personas y no sustituye la "
            "revisión humana. Los conteos sobre fixtures no estiman eficacia real: la inferencia "
            "científica exige corpus nuevo, etiquetado a ciegas, grupos independientes y permiso "
            "de uso. Si el tamaño o las discordancias no alcanzan, la salida correcta es "
            "`NO EJECUTADO` o `NO ESTIMABLE`, no una conclusión."
        )
    if cases:
        st.metric("Casos del corpus actual", len(cases), border=True)
        st.caption("Abre «Estadística» después de comparar para ver los cálculos de esta sesión.")

elif section == "Datos":
    st.header("Preparar datos", icon=":material/database:")
    st.caption("El corpus se valida en memoria. No se muestran cuerpos, remitentes ni contactos.")
    with st.container(border=True):
        st.subheader("01 · Define el origen", icon=":material/verified_user:")
        origin_col, purpose_col = st.columns(2)
        with origin_col:
            kind = st.segmented_control(
                "Origen del corpus", ["Ficticio", "Autorizado"], default="Ficticio", key="kind"
            )
        with purpose_col:
            role = st.segmented_control(
                "Propósito del corpus",
                ["Entrenamiento", "Evaluación independiente"],
                default="Entrenamiento",
                key="role",
            )
        permission = (
            st.text_input("Referencia de autorización (ID opaco, sin secretos)", key="permission")
            if kind == "Autorizado"
            else None
        )
        if kind == "Autorizado":
            st.caption("La referencia declarada no sustituye la revisión del permiso de uso.")
        st.caption("Formato JSONL · máximo 20 MB · solo este dispositivo")
        upload_col, action_col = st.columns([2, 1], vertical_alignment="bottom")
        with upload_col:
            fixture = st.file_uploader("Corpus JSONL", type=["jsonl"], key="dataset")
        with action_col:
            if st.button(
                "Cargar ejemplo local",
                key="demo",
                icon=":material/data_object:",
                width="stretch",
                disabled=kind != "Ficticio" or role != "Entrenamiento",
            ):
                try:
                    sample = demo_cases()
                    st.session_state["cases"] = sample
                    st.session_state["manifest"] = split_manifest(None, sample)
                    st.session_state["use"] = CorpusUse()
                    context_bytes = (
                        Path(__file__).resolve().parents[2] / "datasets" / "context.json"
                    ).read_bytes()
                    context, context_sha = load_context_bytes(context_bytes, use=CorpusUse())
                    st.session_state["context"] = context
                    st.session_state["manifest"]["context_sha256"] = context_sha
                    st.session_state["training"] = st.session_state["comparison"] = None
                    st.session_state["training_model_bytes"] = None
                    st.session_state["comparison_raw"] = None
                    st.success("Ejemplo cargado: fixture ficticio, sin resultados científicos.")
                except ResearchDataError:
                    st.error("No se pudo construir el fixture artificial.")
            if (
                st.button(
                    "Validar archivo",
                    key="load",
                    type="primary",
                    icon=":material/upload_file:",
                    width="stretch",
                    disabled=fixture is None,
                )
                and fixture is not None
            ):
                try:
                    selected_use = CorpusUse(
                        kind="authorized" if kind == "Autorizado" else "fixture",
                        permission_ref=permission or None,
                        role="independent_evaluation"
                        if role == "Evaluación independiente"
                        else "training",
                    )
                    contents = fixture.getvalue()
                    selected = load_research_bytes(contents, use=selected_use)
                    st.session_state["cases"] = selected
                    st.session_state["use"] = selected_use
                    st.session_state["manifest"] = split_manifest(
                        None, selected, raw_bytes=contents, use=selected_use
                    )
                    st.session_state["context"] = None
                    st.session_state["training"] = st.session_state["comparison"] = None
                    st.session_state["training_model_bytes"] = None
                    st.session_state["comparison_raw"] = None
                    st.success("Corpus validado. Carga el contexto para comparar condiciones.")
                except ResearchDataError, OSError, ValueError:
                    st.error("Archivo inválido o grupos insuficientes. Revisa el contrato JSONL.")
    with st.container(border=True):
        st.subheader("02 · Contexto organizacional", icon=":material/account_tree:")
        st.caption("Necesario para comparar señales de identidad. Se conserva solo en memoria.")
        context_upload, context_action = st.columns([2, 1], vertical_alignment="bottom")
        with context_upload:
            context_file = st.file_uploader(
                "Contexto organizacional JSON", type=["json"], key="context_file"
            )
        with context_action:
            if (
                st.button(
                    "Validar contexto",
                    key="load_context",
                    icon=":material/check_circle:",
                    width="stretch",
                    disabled=not cases or context_file is None,
                )
                and context_file is not None
            ):
                try:
                    selected_context, context_sha = load_context_bytes(
                        context_file.getvalue(), use=use
                    )
                    st.session_state["context"] = selected_context
                    st.session_state["manifest"]["context_sha256"] = context_sha
                    st.session_state["comparison"] = None
                    st.session_state["comparison_raw"] = None
                    st.success("Contexto preparado; los contactos no se muestran.")
                except ResearchDataError:
                    st.error("Contexto inválido; revisa estructura, dominios y campos.")
    if st.session_state["manifest"]:
        active = st.session_state["use"]
        counts = st.session_state["manifest"]["counts"]
        total = sum(sum(part.values()) for part in counts.values())
        st.subheader("Vista previa del corpus", icon=":material/table_chart:")
        with st.container(horizontal=True):
            st.metric("Mensajes", total, border=True)
            st.metric(
                "Grupos independientes",
                len({case.group_id for case in st.session_state["cases"]}),
                border=True,
            )
            st.metric(
                "Contexto", "Listo" if st.session_state["context"] else "Pendiente", border=True
            )
        summary = [
            {"partición": name, **part, "total": sum(part.values())}
            for name, part in counts.items()
        ]
        table_col, chart_col = st.columns(2, gap="large")
        with table_col:
            st.dataframe(
                summary,
                hide_index=True,
                alt="Tamaños y etiquetas de entrenamiento, validación y prueba",
            )
        with chart_col:
            st.bar_chart(
                summary,
                x="partición",
                y=["BEC", "LEGITIMATE"],
                stack=True,
                alt="Distribución de BEC y correos legítimos por partición",
            )
        st.caption(f"Corpus activo: {active.kind} · uso: {active.role} · semilla: 20261118")
        with st.expander("Identificadores de reproducibilidad", icon=":material/fingerprint:"):
            st.code(f"dataset_sha256 = {st.session_state['manifest']['dataset_sha256']}")
            if st.session_state["manifest"].get("context_sha256"):
                st.code(f"context_sha256 = {st.session_state['manifest']['context_sha256']}")

elif section == "Entrenamiento":
    st.header("Entrenar un candidato", icon=":material/model_training:")
    st.caption("Texto y metadatos de evaluación permanecen separados durante el entrenamiento.")
    with st.container(border=True):
        st.subheader("Diseño de la búsqueda", icon=":material/tune:")
        with st.container(horizontal=True):
            st.metric("Configuraciones", "12", border=True)
            st.metric("Folds agrupados", "3", border=True)
            st.metric("Partición objetivo", "70 / 15 / 15", border=True)
        st.caption(
            "TF-IDF + regresión logística · selección en train y validation · "
            "modelo mantenido en memoria."
        )
        evaluate_test = st.checkbox(
            "Evaluar test una vez después de congelar la selección",
            key="evaluate_test",
        )
        if use and use.role == "independent_evaluation":
            st.info("Este corpus está reservado para evaluación: no puede entrenar modelos.")
        already_tested = bool(
            use
            and use.kind == "authorized"
            and manifest
            and manifest["dataset_sha256"] in st.session_state["final_test_hashes"]
        )
        if already_tested:
            st.info("El test ya se evaluó en esta sesión; no se repetirá.")
        if st.button(
            "Iniciar entrenamiento",
            icon=":material/play_arrow:",
            type="primary",
            width="stretch",
            disabled=not cases
            or (use is not None and use.role == "independent_evaluation")
            or (evaluate_test and already_tested),
            key="train",
        ):
            try:
                with st.spinner("Ejecutando 36 ajustes locales con validación agrupada…"):
                    trained, model = train_offline(
                        cases,
                        evaluate_test=evaluate_test,
                        use=use,
                        dataset_sha256=manifest["dataset_sha256"],
                        test_lock_dir=final_test_lock_dir(),
                    )
                    trained["provenance"] = {
                        key: manifest[key]
                        for key in (
                            "dataset_sha256",
                            "research_code_sha256",
                            "dependencies",
                            "uv_lock_sha256",
                            "git_commit",
                            "seed",
                            "working_tree_dirty",
                        )
                    }
                    st.session_state["training_model_bytes"] = None
                    if model is not None and (trained.get("selected") or {}).get("threshold"):
                        import joblib

                        output = io.BytesIO()
                        joblib.dump(model, output)
                        st.session_state["training_model_bytes"] = output.getvalue()
                        trained["model_sha256"] = hashlib.sha256(output.getvalue()).hexdigest()
                st.session_state["training"] = trained
                if trained["test_status"] == "AUTHORIZED_TEST_EVALUATED":
                    st.session_state["final_test_hashes"].add(manifest["dataset_sha256"])
                st.success("Búsqueda terminada. Interpreta estos datos según el origen del corpus.")
            except ResearchDataError, ValueError:
                st.error("No hay grupos o clases suficientes para una CV válida.")
    if not cases:
        st.info("Carga un corpus o el ejemplo local en Datos para activar el entrenamiento.")
    trained = st.session_state["training"]
    if trained:
        st.subheader("Resultado de la ejecución", icon=":material/query_stats:")
        st.badge(
            "Ejemplo ficticio" if use.kind == "fixture" else "Corpus autorizado declarado",
            color="orange" if use.kind == "fixture" else "blue",
        )
        selected = trained["selected"]
        with st.container(horizontal=True):
            st.metric("Candidatos evaluados", len(trained["cv"]), border=True)
            st.metric(
                "Umbral elegido",
                selected["threshold"] if selected else "Sin candidato",
                border=True,
            )
            st.metric(
                "Prueba final",
                "No ejecutada" if trained["test"] is None else "Ejecutada",
                border=True,
            )
        trials = [
            {
                "configuración": f"{i + 1:02}",
                "n-gramas": str(row["ngram_range"]),
                "C": row["C"],
                "balance": row["class_weight"] or "ninguno",
                "recall CV": row["mean_recall"],
                "FPR CV": row["mean_fpr"],
                "dispersión": row["dispersion"],
            }
            for i, row in enumerate(trained["cv"])
        ]
        with st.container(border=True):
            st.markdown("**Balance de la validación cruzada**")
            st.bar_chart(
                trials,
                x="configuración",
                y=["recall CV", "FPR CV"],
                alt="Recall y falsos positivos de los candidatos en validación cruzada",
            )
        with st.expander("Configuraciones y detalles técnicos", icon=":material/table_chart:"):
            st.dataframe(
                trials,
                hide_index=True,
                alt="Configuraciones y métricas de validación cruzada",
            )
            st.json(
                {
                    key: trained[key]
                    for key in (
                        "baseline",
                        "selected",
                        "calibration",
                        "resource_budget",
                        "validation",
                        "test_status",
                        "test",
                    )
                }
            )
        st.download_button(
            "Descargar reporte de entrenamiento",
            json.dumps(trained, ensure_ascii=False, indent=2),
            file_name="bec-guard-training-report.json",
            mime="application/json",
            key="download_training",
            icon=":material/download:",
        )
        if st.session_state["training_model_bytes"] is not None:
            st.download_button(
                "Descargar modelo local (joblib)",
                st.session_state["training_model_bytes"],
                file_name="bec-guard-model.joblib",
                mime="application/octet-stream",
                key="download_model",
                icon=":material/download:",
            )
            st.caption(
                "El reporte incluye el SHA-256 del modelo descargado. Un fixture no puede "
                "activar assist en el programa funcional."
            )

elif section == "Comparación":
    st.header("Comparar detectores", icon=":material/compare_arrows:")
    st.caption(
        "Siete condiciones sobre los mismos mensajes; riesgo y generación de alertas separados."
    )
    with st.container(border=True):
        st.subheader("Configura la comparación", icon=":material/tune:")
        hypothetical = st.toggle("Simular un score semántico constante de 50", key="fake_semantic")
        if hypothetical:
            st.warning("Score hipotético: no es una respuesta observada de IA.")
        else:
            st.caption("Sin cache semántico, C2/C3/C5/C6 se marcarán NO EJECUTADAS.")
        main_cache_col, context_cache_col = st.columns(2, gap="large")
        with main_cache_col:
            cache_file = st.file_uploader(
                "Cache de scores por caso (JSON)", type=["json"], key="semantic_cache"
            )
        with context_cache_col:
            no_context_file = st.file_uploader(
                "Cache alternativo sin contexto para C4", type=["json"], key="no_context_cache"
            )
        with st.expander("Referencia para el cache sin contexto", icon=":material/fingerprint:"):
            st.code(f"context_sha256 = {EMPTY_CONTEXT_SHA256}")
        if st.button(
            "Ejecutar comparación offline",
            icon=":material/analytics:",
            type="primary",
            width="stretch",
            disabled=not cases or not st.session_state["context"],
            key="compare",
        ):
            try:
                scores = {case.case_id: 50 for case in cases} if hypothetical else None
                source = "HYPOTHETICAL" if hypothetical else None
                semantic_provenance = None
                no_context_scores = None
                no_context_semantic_provenance = None
                no_context_hash = None
                if cache_file is not None and not hypothetical:
                    if use.kind != "authorized":
                        raise ResearchDataError("Real cache requires an authorized corpus")
                    scores, semantic_provenance = load_semantic_cache(
                        cache_file.getvalue(),
                        dataset_sha256=manifest["dataset_sha256"],
                        context_sha256=manifest["context_sha256"],
                        case_ids={case.case_id for case in cases},
                    )
                    source = "CACHED_AUTHORIZED"
                    if no_context_file is not None:
                        no_context_scores, no_context_semantic_provenance = load_semantic_cache(
                            no_context_file.getvalue(),
                            dataset_sha256=manifest["dataset_sha256"],
                            context_sha256=EMPTY_CONTEXT_SHA256,
                            case_ids={case.case_id for case in cases},
                        )
                        no_context_hash = no_context_semantic_provenance["cache_sha256"]
                raw = compare_offline(
                    cases,
                    st.session_state["context"],
                    semantic_scores=scores,
                    semantic_source=source,
                    semantic_provenance=semantic_provenance,
                    no_context_scores=no_context_scores,
                    no_context_semantic_provenance=no_context_semantic_provenance,
                    no_context_cache_sha256=no_context_hash,
                    use=use,
                )
                st.session_state["comparison_raw"] = raw
                st.session_state["comparison"] = summarize_experiment(raw, provenance=manifest)
                st.success("Comparación completada localmente, sin llamadas a proveedores.")
            except ResearchDataError:
                st.error("No se pudo comparar: revisa corpus, contexto y caches.")
    if not cases or not st.session_state["context"]:
        st.info("Carga corpus y contexto en Datos para habilitar la comparación.")
    report = st.session_state["comparison"]
    if report:
        st.subheader("Lectura de condiciones", icon=":material/bar_chart:")
        if report["semantic_source"] == "HYPOTHETICAL":
            st.badge("Simulación hipotética", color="orange")
        elif report["semantic_source"] == "CACHED_AUTHORIZED":
            st.badge("Scores cacheados con procedencia", color="blue")
        else:
            st.badge("Solo reglas y fallback", color="gray")
        rows = []
        for name, stats in report["conditions"].items():
            if stats["status"] == "NOT_RUN":
                rows.append({"condición": name, "estado": "NO EJECUTADA"})
            else:
                rows.append(
                    {
                        "condición": name,
                        "estado": stats["status"],
                        "casos": stats["total"],
                        "TP": stats["alerts"]["tp"],
                        "FP": stats["alerts"]["fp"],
                        "TN": stats["alerts"]["tn"],
                        "FN": stats["alerts"]["fn"],
                        "fallback": stats["fallback"],
                        "recall alertas": stats["alerts"]["recall"],
                        "FPR alertas": stats["alerts"]["fpr"],
                        "cobertura score": stats["score_coverage"],
                        "cobertura semántica": stats["semantic_coverage"],
                    }
                )
        visible = [row for row in rows if "recall alertas" in row]
        with st.container(horizontal=True):
            st.metric("Condiciones ejecutadas", len(visible), border=True)
            st.metric("Condiciones sin ejecutar", len(rows) - len(visible), border=True)
            st.metric("Mensajes comparados", visible[0]["casos"] if visible else "—", border=True)
        with st.container(border=True):
            st.markdown("**Matriz de confusión por condición**")
            if visible:
                st.bar_chart(
                    visible,
                    x="condición",
                    y=["TP", "FP", "FN", "TN"],
                    stack=True,
                    alt="Casos por resultado de alerta en cada condición evaluada",
                )
                st.caption(
                    "El fixture puede dejar recall y FPR en cero: sus textos no activan las reglas."
                )
            else:
                st.caption("Ninguna condición se ejecutó; revisa caches y contexto.")
        with st.expander("Matriz de resultados y cobertura", icon=":material/table_chart:"):
            st.dataframe(rows, hide_index=True, alt="Comparación de alertas y cobertura C1 a C7")
        if report["conditions"]["C4"]["status"] == "NOT_RUN":
            st.caption("C4 requiere un cache adicional generado sin contexto.")

elif section == "Estadística":
    st.header("Estadística del experimento", icon=":material/query_stats:")
    st.caption("Intervalos, contrastes pareados y curvas calculados sobre la comparación actual.")
    raw_experiment = st.session_state["comparison_raw"]
    report = st.session_state["comparison"]
    if raw_experiment is None or not report:
        with st.container(border=True):
            st.subheader("Todavía no hay datos que analizar", icon=":material/pending_actions:")
            st.markdown(
                "Ejecuta «Comparación» o prepara aquí una demostración con score semántico "
                "hipotético de 50 para habilitar C2/C3/C5/C6. Es una simulación, no una "
                "respuesta de IA."
            )
            if st.button(
                "Preparar demostración estadística",
                icon=":material/science:",
                type="primary",
                width="stretch",
                key="stats_prepare",
            ):
                if not cases or not st.session_state["context"]:
                    st.error("Carga primero un corpus y su contexto en «Datos».")
                else:
                    scores = {case.case_id: 50 for case in cases}
                    raw = compare_offline(
                        cases,
                        st.session_state["context"],
                        semantic_scores=scores,
                        semantic_source="HYPOTHETICAL",
                        use=use,
                    )
                    st.session_state["comparison_raw"] = raw
                    st.session_state["comparison"] = summarize_experiment(raw, provenance=manifest)
                    st.rerun()
    else:
        stats = technical_statistics(raw_experiment)
        st.warning(stats["disclaimer"])
        executed = {
            key: value
            for key, value in stats["conditions"].items()
            if value.get("status") != "NOT_RUN"
        }
        if not executed:
            st.info("Ninguna condición se ejecutó; revisa caches y contexto.")
        else:
            options = list(executed)
            default = "C3" if "C3" in options else options[0]
            with st.container(horizontal=True, vertical_alignment="bottom"):
                selected = st.selectbox(
                    "Condición para el detalle",
                    options,
                    index=options.index(default),
                    key="stats_condition",
                )
                st.metric("Base", stats["basis"], border=True)
                st.metric("Inferencia científica", "NO EJECUTADA", border=True)
            condition = executed[selected]
            confusion = condition["confusion"]

            def as_percent(value):
                return "—" if value is None else f"{value:.1%}"

            with st.container(horizontal=True):
                st.metric("Recall alertas", as_percent(confusion["recall"]), border=True)
                st.metric("FPR alertas", as_percent(confusion["fpr"]), border=True)
                st.metric("Precisión", as_percent(confusion["precision"]), border=True)
                st.metric("F1", as_percent(condition["f1"]), border=True)

            confusion_col, wilson_col = st.columns([3, 2], gap="large")
            with confusion_col:
                with st.container(border=True):
                    st.markdown(f"**Matriz de confusión · {selected}**")
                    st.bar_chart(
                        [
                            {
                                "resultado": selected,
                                "TP": confusion["tp"],
                                "FP": confusion["fp"],
                                "FN": confusion["fn"],
                                "TN": confusion["tn"],
                            }
                        ],
                        x="resultado",
                        y=["TP", "FP", "FN", "TN"],
                        stack=True,
                        alt="Matriz de confusión de la condición seleccionada",
                    )
                    st.caption(
                        f"Umbral de alerta {condition['alert_threshold']} · "
                        f"{condition['scored']} de {condition['total']} casos con score · "
                        f"{condition['errors']} errores · {condition['fallback']} fallback."
                    )
            with wilson_col:
                with st.container(border=True):
                    st.markdown("**Intervalos Wilson 95 %**")
                    compact = []
                    for label, rate in (
                        ("Recall", condition["recall_ci"]),
                        ("FPR", condition["fpr_ci"]),
                        ("Especificidad", condition["specificity_ci"]),
                    ):
                        interval = None if rate is None else rate["wilson95"]
                        compact.append(
                            {
                                "medida": label,
                                "valor": as_percent(None if rate is None else rate["value"]),
                                "IC95": (
                                    "—"
                                    if interval is None
                                    else f"{interval['low']:.1%} – {interval['high']:.1%}"
                                ),
                            }
                        )
                    st.dataframe(compact, hide_index=True, alt="Intervalos de confianza Wilson")

            st.subheader("Métricas por condición", icon=":material/table_rows:")
            table = []
            for name, values in executed.items():
                alerts = values["confusion"]
                table.append(
                    {
                        "condición": name,
                        "n": values["scored"],
                        "TP": alerts["tp"],
                        "FP": alerts["fp"],
                        "TN": alerts["tn"],
                        "FN": alerts["fn"],
                        "recall": as_percent(alerts["recall"]),
                        "FPR": as_percent(alerts["fpr"]),
                        "precisión": as_percent(alerts["precision"]),
                        "F1": as_percent(values["f1"]),
                        "mediana ms": values["latency_ms"]["median"],
                        "p95 ms": values["latency_ms"]["p95"],
                    }
                )
            st.dataframe(table, hide_index=True, alt="Métricas de alerta por condición")

            st.subheader("Contrastes pareados", icon=":material/balance:")
            paired = stats["paired"]
            if paired["status"] != "ESTIMATED_TECHNICAL_ONLY":
                reason = paired.get("reason", paired["status"])
                st.info(
                    "Contraste no estimable con este diseño o tamaño "
                    f"(`{reason}`). Se muestran solo descriptivos."
                )
            else:
                rows = []
                for name, values in paired["comparisons"].items():
                    recall_ci = values["ci95_group_bootstrap"].get("recall")
                    fpr_ci = values["ci95_group_bootstrap"].get("fpr")
                    rows.append(
                        {
                            "contraste": name.replace("_", " "),
                            "pares": values["pairs"],
                            "grupos": values["groups"],
                            "Δ recall": f"{values['difference_recall']:+.1%}"
                            if values["difference_recall"] is not None
                            else "—",
                            "IC95 Δ recall": (
                                "—"
                                if recall_ci is None
                                else f"[{recall_ci['lower']:+.1%}, {recall_ci['upper']:+.1%}]"
                            ),
                            "Δ FPR": f"{values['difference_fpr']:+.1%}"
                            if values["difference_fpr"] is not None
                            else "—",
                            "IC95 Δ FPR": (
                                "—"
                                if fpr_ci is None
                                else f"[{fpr_ci['lower']:+.1%}, {fpr_ci['upper']:+.1%}]"
                            ),
                            "discordancias": values["discordances"],
                            "p McNemar": (
                                "no aplica"
                                if values["p_mcnemar_exact"] is None
                                else f"{values['p_mcnemar_exact']:.4f}"
                            ),
                            "p Holm": (
                                "no aplica"
                                if values["p_holm"] is None
                                else f"{values['p_holm']:.4f}"
                            ),
                        }
                    )
                st.dataframe(rows, hide_index=True, alt="Contrastes pareados C3 contra C1 y C2")
                st.caption(
                    "Bootstrap por grupos con semilla "
                    f"{stats['seed']} · {stats['resamples']} réplicas · "
                    "McNemar exacto solo con ≥10 discordancias · Holm si ambos contrastes "
                    "preespecificados alcanzan ese mínimo."
                )

            curves_col, types_col = st.columns(2, gap="large")
            with curves_col:
                ranking = condition["ranking"]
                if ranking and ranking.get("status") == "ESTIMATED_DESCRIPTIVE":
                    st.metric(
                        "Average precision", f"{ranking['average_precision']:.3f}", border=True
                    )
                    st.metric("ROC-AUC", f"{ranking['roc_auc']:.3f}", border=True)
                else:
                    st.info("Average precision y ROC-AUC no estimables con esta cobertura.")
                curves = condition["curves"]
                if curves.get("status") == "ESTIMATED_DESCRIPTIVE":
                    with st.expander("Curvas PR y ROC", icon=":material/show_chart:"):
                        if len(curves["precision_recall"]) > 1:
                            st.caption("Precisión-recall (puntos por umbral de score)")
                            st.line_chart(
                                curves["precision_recall"],
                                x="recall",
                                y="precision",
                                alt="Curva de precisión y recall",
                            )
                        if len(curves["roc"]) > 1:
                            st.caption("ROC (puntos por umbral de score)")
                            st.line_chart(
                                curves["roc"],
                                x="fpr",
                                y="tpr",
                                alt="Curva ROC",
                            )
            with types_col:
                st.markdown("**Resultado por tipo BEC**")
                type_rows = [
                    {
                        "tipo": name,
                        "total": values["total"],
                        "detectados": values["detected"],
                        "alertados": values["alerted"],
                    }
                    for name, values in condition["by_bec_type"].items()
                ]
                if type_rows:
                    st.bar_chart(
                        type_rows,
                        x="tipo",
                        y=["detectados", "alertados"],
                        alt="Detecciones y alertas por tipo de BEC",
                    )
                else:
                    st.caption("La condición no tiene casos BEC con tipo etiquetado.")
                hard = condition["hard_negatives"]
                st.metric(
                    "Falsas alarmas en negativos difíciles",
                    f"{hard['false_alerts']} / {hard['total']}",
                    border=True,
                )

            with st.expander("Cobertura, latencia y descarga", icon=":material/download:"):
                st.json(
                    {
                        "base": stats["basis"],
                        "origen_semántico": stats["semantic_source"],
                        "políticas": stats["policies"],
                        "condición": selected,
                        "cobertura": {
                            "casos": condition["total"],
                            "con_score": condition["scored"],
                            "errores": condition["errors"],
                            "fallback": condition["fallback"],
                        },
                        "latencia_ms": condition["latency_ms"],
                        "contrastes": stats["paired"],
                    }
                )
            st.download_button(
                "Descargar estadística JSON",
                json.dumps(stats, ensure_ascii=False, indent=2),
                file_name="bec-guard-statistics.json",
                mime="application/json",
                key="download_stats",
                icon=":material/download:",
            )
            st.caption(
                "Cálculos técnicos de la sesión. Con corpus fixture o score hipotético no "
                "constituyen inferencia científica."
            )

elif section == "Transferencia":
    st.header("Transferencia a fuentes públicas", icon=":material/travel_explore:")
    st.caption(
        "Compara el modelo congelado con etiquetas de terceros sin cargar correos en la interfaz. "
        "El entrenamiento y los CSV se procesan localmente por CLI."
    )
    uploaded_report = st.file_uploader(
        "Informe externo agregado (JSON)", type=["json"], key="public_report"
    )
    if uploaded_report is None:
        st.info(
            "Carga un JSON agregado de external_benchmark, public_retraining o "
            "auxiliary_phishing_benchmark."
        )
    else:
        try:
            public_summary = summarize_public_report(uploaded_report.getvalue())
        except ValueError as error:
            st.error(str(error))
        else:
            st.caption(f"Modelo(s) SHA-256: {public_summary['model_sha256']}")
            st.dataframe(
                public_summary["rows"],
                hide_index=True,
                alt="Conteos y tasas del modelo congelado por fuente pública",
            )
            if public_summary["gate"]:
                st.badge(
                    "Objetivos proxy: " + public_summary["gate"],
                    color="orange",
                    icon=":material/monitoring:",
                )
            if public_summary["status"] == AUX:
                st.warning(
                    "Phishing genérico no equivale a BEC. El corpus es sintético y no tiene "
                    "subtipo BEC por fila; estas tasas no son recall BEC ni habilitan assist."
                )
            else:
                st.warning(
                    "Solo diagnóstico entre fuentes. BEC-2 es sintético; el ham histórico no "
                    "certifica falsos positivos operativos. Estos informes no habilitan assist."
                )

elif section == "Informe":
    st.header("Informe del experimento", icon=":material/description:")
    st.caption(
        "Solo agregados, versiones y procedencia: sin contenido ni predicciones individuales."
    )
    report = st.session_state["comparison"]
    if not report:
        with st.container(border=True):
            st.subheader("Aún no hay informe", icon=":material/pending_actions:")
            st.markdown("Carga un corpus y ejecuta una comparación para preparar la exportación.")
    else:
        if report["status"] == "TECHNICAL_FIXTURE_ONLY":
            st.warning("Este informe usa fixtures y no permite inferir eficacia real.")
        semantic_labels = {
            "NOT_RUN": "Sin cache",
            "HYPOTHETICAL": "Score hipotético",
            "CACHED_AUTHORIZED": "Cache autorizado",
        }
        inference = report["scientific_inference"]
        if inference.startswith("DESCRIPTIVE_ONLY"):
            inference_label = "Solo descriptivo"
        elif inference == "NOT_EXECUTED":
            inference_label = "No ejecutada"
        else:
            inference_label = inference
        summary_col, coverage_col, inference_col = st.columns(3, border=True)
        with summary_col:
            st.caption("ORIGEN")
            st.metric(
                "Semántica",
                semantic_labels.get(report["semantic_source"], report["semantic_source"]),
            )
        with coverage_col:
            st.caption("EJECUCIÓN")
            st.metric(
                "Condiciones",
                len([c for c in report["conditions"].values() if c["status"] != "NOT_RUN"]),
            )
        with inference_col:
            st.caption("INFERENCIA")
            st.metric("Estado", inference_label)
        with st.container(border=True):
            st.subheader("Informe listo para exportar", icon=":material/file_download:")
            st.caption(
                "Incluye matrices de confusión, cobertura, hashes y límites. "
                "Nunca incluye cuerpos ni direcciones."
            )
            st.download_button(
                "Descargar informe JSON",
                json.dumps(report, ensure_ascii=False, indent=2),
                file_name="bec-guard-research-report.json",
                mime="application/json",
                key="download_report",
                icon=":material/download:",
                type="primary",
            )
        with st.expander("Estadística pareada y limitaciones", icon=":material/query_stats:"):
            st.json(report["paired_statistics"])
        with st.expander("Procedencia y versiones", icon=":material/fingerprint:"):
            st.json(
                {
                    "estado": report["status"],
                    "origen_semántico": report["semantic_source"],
                    "condiciones": report["condition_counts"],
                    "políticas": report["policies"],
                    "procedencia": report["provenance"],
                }
            )
