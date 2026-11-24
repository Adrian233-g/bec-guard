"""Proyección de informes públicos agregados para el laboratorio; nunca muestra correos."""

import json
import re

MAX_REPORT_BYTES = 1_000_000
V1 = "CROSS_SOURCE_SYNTHETIC_BEC_AND_PUBLIC_HAM_DIAGNOSTIC_ONLY"
V2 = "PUBLIC_DIAGNOSTIC_TRAINING_ONLY"
AUX = "SYNTHETIC_EXTERNAL_GENERIC_PHISHING_STRESS_ONLY"


def _summarize_auxiliary(report: dict) -> dict:
    if report.get("assist_eligible") is not False or not isinstance(report.get("models"), dict):
        raise ValueError("Informe auxiliar inválido")
    models = report["models"]
    if set(models) != {"v1", "v2"}:
        raise ValueError("Faltan modelos auxiliares")
    rows = []
    hashes = []
    cohort_sizes = None
    for name in ("v1", "v2"):
        item = models[name]
        if (
            not isinstance(item, dict)
            or item.get("bec_recall") != "NOT_ESTIMABLE_NO_BEC_SUBTYPE_LABEL"
        ):
            raise ValueError("Informe auxiliar no identifica el límite BEC")
        digest = item.get("model_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Modelo auxiliar sin SHA-256")
        hashes.append(f"{name}: {digest}")
        for label, count_key, flagged_key, rate_key, metric in (
            (
                "legítimo sintético",
                "benign_count",
                "benign_false_alarms",
                "benign_fpr_synthetic",
                "FPR sintética",
            ),
            (
                "phishing genérico",
                "generic_phishing_count",
                "generic_phishing_flagged",
                "generic_phishing_flag_rate",
                "Marcación (no recall BEC)",
            ),
        ):
            count, flagged, rate = (item.get(count_key), item.get(flagged_key), item.get(rate_key))
            if (
                type(count) is not int
                or type(flagged) is not int
                or count < 1
                or not 0 <= flagged <= count
                or type(rate) not in (int, float)
                or abs(rate - flagged / count) > 1e-9
            ):
                raise ValueError("Denominadores auxiliares inconsistentes")
            rows.append(
                {
                    "fuente": f"{name} / {label}",
                    "evaluados": count,
                    "positivos del modelo": flagged,
                    "métrica": metric,
                    "tasa": f"{rate:.1%}",
                }
            )
        sizes = (item["benign_count"], item["generic_phishing_count"])
        if cohort_sizes is not None and sizes != cohort_sizes:
            raise ValueError("Los modelos auxiliares usaron cohortes diferentes")
        cohort_sizes = sizes
    corpus = report.get("corpus")
    if not isinstance(corpus, dict) or corpus.get("unique_labels") != {
        "0": cohort_sizes[0],
        "1": cohort_sizes[1],
    }:
        raise ValueError("El corpus auxiliar y los modelos no coinciden")
    return {
        "status": AUX,
        "model_sha256": " · ".join(hashes),
        "gate": None,
        "rows": rows,
    }


def summarize_public_report(contents: bytes) -> dict:
    if len(contents) > MAX_REPORT_BYTES:
        raise ValueError("El informe agregado supera 1 MB")
    try:
        report = json.loads(contents)
    except ValueError:
        raise ValueError("El informe no es JSON válido") from None
    if not isinstance(report, dict) or report.get("status") not in (V1, V2, AUX):
        raise ValueError("Estado de informe público desconocido")
    if report["status"] == AUX:
        return _summarize_auxiliary(report)
    model_sha = report.get("model_sha256")
    if not isinstance(model_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", model_sha):
        raise ValueError("Falta el identificador del modelo")
    cohorts = report.get("cohorts") if report["status"] == V1 else report.get("external_test")
    expected = (
        ("bec2", "enron", "ceas08")
        if report["status"] == V1
        else (
            "bec2",
            "ceas08_ham",
        )
    )
    if not isinstance(cohorts, dict) or set(cohorts) != set(expected):
        raise ValueError("Faltan fuentes externas")
    rows = []
    for source in expected:
        item = cohorts[source]
        if not isinstance(item, dict):
            raise ValueError("Conteos de fuente inválidos")
        positive = source == "bec2"
        keys = ("tp", "fn") if positive else ("fp", "tn")
        if any(type(item.get(key)) is not int or item[key] < 0 for key in keys):
            raise ValueError("Conteos de fuente inválidos")
        count = item[keys[0]] + item[keys[1]]
        if count < 1 or item.get("evaluated") != count:
            raise ValueError("Denominadores de fuente inconsistentes")
        rate = item[keys[0]] / count
        metric = "recall" if positive else "fpr"
        if type(item.get(metric)) not in (int, float) or abs(item[metric] - rate) > 1e-9:
            raise ValueError("Tasa de fuente inconsistente")
        rows.append(
            {
                "fuente": source,
                "evaluados": count,
                "positivos del modelo": item[keys[0]],
                "métrica": "Recall sintético" if positive else "FPR en ham",
                "tasa": f"{rate:.1%}",
            }
        )
    return {
        "status": report["status"],
        "model_sha256": model_sha,
        "gate": report.get("diagnostic_gate") if report["status"] == V2 else None,
        "rows": rows,
    }
