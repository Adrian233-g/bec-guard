"""Controlled PDF/XLSX representations of the same privacy-limited report."""

from datetime import UTC, datetime
from html import escape
from io import BytesIO
from math import ceil

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.services.reporting import OperationalReport

DISCLAIMER = "Los scores representan una evaluación del sistema y no probabilidades de fraude."
LABELS = {
    "LOW": "Bajo",
    "MEDIUM": "Medio",
    "HIGH": "Alto",
    "CRITICAL": "Crítico",
    "OPEN": "Abierta",
    "UNDER_REVIEW": "En revisión",
    "CLOSED": "Cerrada",
    "CONFIRMED_BEC": "BEC confirmado",
    "FALSE_POSITIVE": "Falso positivo",
    "EXECUTIVE_IMPERSONATION": "Suplantación ejecutiva",
    "VENDOR_FRAUD": "Fraude de proveedor",
    "BANK_ACCOUNT_CHANGE": "Cambio de cuenta",
    "SENSITIVE_DATA_REQUEST": "Solicitud de datos",
    "OTHER": "Otro patrón BEC",
    "COMPLETED": "IA completa",
    "FALLBACK": "Solo reglas",
    "open": "Abiertas",
    "under_review": "En revisión",
    "closed": "Cerradas",
    "confirmed_bec": "BEC confirmados",
    "false_positive": "Falsos positivos",
}


def label(value) -> str:
    return LABELS.get(value, str(value)) if value is not None else "Sin clasificar"


def summary_rows(report: OperationalReport) -> list[list]:
    s = report.summary
    return [
        ["Correos recibidos", s["emails_total"]],
        ["Análisis completos con IA", s["analyses_completed"]],
        ["Análisis limitados a reglas", s["analyses_fallback"]],
        ["Errores de análisis", s["analyses_error"]],
        *[[label(k), v] for k, v in s["alerts"].items()],
        *[[label(k), v] for k, v in s["verdicts"].items()],
    ]


def distribution_tables(
    report: OperationalReport,
) -> list[tuple[str, list[str], list[list], str, list[int]]]:
    summary = report.summary
    denominators = summary["distribution_denominators"]
    percentages = summary["distribution_percentages"]
    risk_rows = [
        [
            label(key),
            count,
            denominators["risk"],
            percentages["risk"].get(key, 0) / 100,
        ]
        for key, count in summary["risk_distribution"].items()
    ]
    type_rows = [
        [
            label(item["bec_type"]),
            item["count"],
            denominators["bec_type"],
            item.get("percentage", 0) / 100,
        ]
        for item in summary["bec_type_distribution"]
    ]
    alert_rows = [
        [
            label(key),
            count,
            denominators["alert_status"],
            percentages["alert_status"].get(key, 0) / 100,
        ]
        for key, count in summary["alerts"].items()
    ]
    verdict_rows = [
        [
            label(key),
            count,
            denominators["verdict"],
            percentages["verdict"].get(key, 0) / 100,
        ]
        for key, count in summary["verdicts"].items()
    ]
    headers = ["Categoría", "Cantidad", "Denominador", "Porcentaje"]
    return [
        (
            "Distribución de riesgo",
            headers,
            risk_rows,
            "Base: análisis con nivel de riesgo asignado en el periodo. "
            "No es una métrica de calidad del detector.",
            [32, 16, 20, 16],
        ),
        (
            "Tipos BEC",
            headers,
            type_rows,
            "Base: análisis con un tipo BEC identificado. "
            "Un tipo ausente no se incluye en esta distribución.",
            [38, 16, 20, 16],
        ),
        (
            "Estados de alerta",
            headers,
            alert_rows,
            "Base: alertas creadas en el periodo. El estado es el estado actual, "
            "no un historial temporal.",
            [32, 16, 20, 16],
        ),
        (
            "Veredictos humanos",
            headers,
            verdict_rows,
            "Base: alertas con decisión humana registrada. Las alertas sin decisión "
            "no son BEC confirmado ni falso positivo.",
            [32, 16, 20, 16],
        ),
    ]


def xlsx_bytes(report: OperationalReport) -> bytes:
    book = Workbook()
    book.remove(book.active)
    tables = [
        (
            "Resumen",
            ["Indicador", "Cantidad"],
            summary_rows(report),
            "Los conteos son operativos y no representan sensibilidad o precisión poblacional.",
            [42, 20],
        ),
        *distribution_tables(report),
        (
            "Alertas",
            [
                "Alerta ID",
                "Creada (UTC)",
                "Score",
                "Riesgo",
                "Tipo BEC",
                "Modo de análisis",
                "Estado",
                "Veredicto",
                "Responsable",
            ],
            [
                [
                    str(a.id),
                    a.created_at.astimezone(UTC).replace(tzinfo=None),
                    a.risk_score,
                    label(a.risk_level),
                    label(a.bec_type),
                    label(a.analysis_mode),
                    label(a.status),
                    label(a.verdict) if a.verdict else "Sin decisión",
                    a.assigned_to_name or "Sin asignar",
                ]
                for a in report.alerts
            ],
            "Cada alerta conserva separado su modo de análisis y su decisión humana.",
            [39, 23, 10, 14, 23, 20, 19, 21, 30],
        ),
    ]
    for title, headers, rows, interpretation, widths in tables:
        sheet = book.create_sheet(title)
        sheet.sheet_view.showGridLines = False
        sheet.append(["BEC Guard | Reporte operativo"])
        sheet.append([report.period])
        sheet.append(["Generado (UTC)", report.generated_at.astimezone(UTC).replace(tzinfo=None)])
        sheet.append([])
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        data_last_row = sheet.max_row
        sheet.append([])
        sheet.append(["Interpretación", interpretation])
        interpretation_row = sheet.max_row
        sheet.freeze_panes = "A6"
        sheet.auto_filter.ref = f"A5:{get_column_letter(len(headers))}{max(5, data_last_row)}"
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(2, len(headers)))
        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(2, len(headers)))
        sheet.merge_cells(
            start_row=interpretation_row,
            start_column=2,
            end_row=interpretation_row,
            end_column=max(2, len(headers)),
        )
        sheet.row_dimensions[1].height = 30
        sheet.row_dimensions[5].height = 28
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # Never Excel formulas from names.
                cell.font = Font(name="Calibri", size=11, color="233747")
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if isinstance(cell.value, datetime):
                    cell.number_format = "yyyy-mm-dd hh:mm:ss"
                elif isinstance(cell.value, int):
                    cell.number_format = "#,##0"
                elif title != "Resumen" and cell.column == 4 and 6 <= cell.row <= data_last_row:
                    cell.number_format = "0.0%"
                if cell.row == 5:
                    cell.fill = PatternFill("solid", fgColor="172E3F")
                    cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                elif cell.row > 5:
                    if cell.row % 2 == 0:
                        cell.fill = PatternFill("solid", fgColor="F1F5F7")
                    sheet.row_dimensions[cell.row].height = 34 if title == "Alertas" else 25
        for row in sheet.iter_rows(min_row=6):
            lines = 1
            for cell in row:
                value = cell.value
                text = (
                    value.strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(value, datetime)
                    else str(value or "")
                )
                width = widths[cell.column - 1]
                lines = max(
                    lines,
                    sum(max(1, ceil(len(part) / max(1, width - 2))) for part in text.split("\n")),
                )
            sheet.row_dimensions[row[0].row].height = max(
                34 if title == "Alertas" else 25, lines * 15 + 6
            )
        sheet.cell(interpretation_row, 1).font = Font(
            name="Calibri", size=11, bold=True, color="172E3F"
        )
        sheet["A1"].font = Font(name="Calibri", size=16, bold=True, color="172E3F")
        sheet.page_setup.orientation = "landscape" if title == "Alertas" else "portrait"
        sheet.print_title_rows = "1:5"
    book["Resumen"].append([])
    book["Resumen"].append([DISCLAIMER])
    final_row = book["Resumen"].max_row
    book["Resumen"].merge_cells(
        start_row=final_row, start_column=1, end_row=final_row, end_column=2
    )
    book["Resumen"].row_dimensions[final_row].height = 38
    book["Resumen"].cell(final_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    output = BytesIO()
    try:
        book.save(output)
        return output.getvalue()
    finally:
        book.close()
        output.close()


def pdf_html(report: OperationalReport) -> str:
    def table(headers, rows, css=""):
        head = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
        )
        if not body:
            body = f'<tr><td colspan="{len(headers)}">Sin registros en el periodo.</td></tr>'
        return f'<table class="{css}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    sections = "<h2>Resumen ejecutivo</h2>" + table(["Indicador", "Cantidad"], summary_rows(report))
    for title, headers, rows, interpretation, _widths in distribution_tables(report):
        display_rows = [row[:3] + [f"{row[3] * 100:.1f}%"] for row in rows]
        sections += (
            f"<section><h2>{escape(title)}</h2>"
            + table(headers, display_rows)
            + f'<p class="interpretation">{escape(interpretation)}</p></section>'
        )
    sections += (
        '<section class="alert-list"><h2>Alertas del periodo</h2>'
        + table(
            [
                "Alerta / creada UTC",
                "Score / riesgo",
                "Tipo BEC",
                "Modo de análisis",
                "Estado / veredicto",
                "Responsable",
            ],
            [
                [
                    f"{a.id}\n{a.created_at.astimezone(UTC):%Y-%m-%d %H:%M}",
                    f"{a.risk_score} / {label(a.risk_level)}",
                    label(a.bec_type),
                    label(a.analysis_mode),
                    f"{label(a.status)} / {label(a.verdict) if a.verdict else 'Sin decisión'}",
                    a.assigned_to_name or "Sin asignar",
                ]
                for a in report.alerts
            ],
            "alerts",
        )
        + "</section>"
    )
    return (
        """<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>BEC Guard - Reporte operativo</title>
<style>

@page {
  size: A4; margin: 16mm 15mm 21mm;
  @bottom-left { content: "BEC Guard | Reporte operativo"; font-size: 8pt; color: #586c7a; }
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 8pt; color: #586c7a; }
}
body { font-family: "DejaVu Sans", sans-serif; font-size: 9pt; color: #233747; line-height: 1.45; }
header { border-bottom: 3px solid #126b70; padding-bottom: 12pt; margin-bottom: 18pt; }
header strong { font-size: 18pt; color: #172e3f; }
h1 { font-size: 15pt; font-weight: normal; margin: 6pt 0; }
header p { font-size: 8pt; margin: 3pt 0; color: #586c7a; }
h2 { font-size: 11pt; color: #172e3f; margin: 17pt 0 7pt; break-after: avoid; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td {
  text-align: left; vertical-align: top; padding: 6pt 8pt;
  border-bottom: 1px solid #d5dfe5; overflow-wrap: anywhere; white-space: pre-wrap;
}
th { background: #e7eff2; font-size: 8pt; }
th:last-child, td:last-child { width: 29%; }
tr { break-inside: avoid; }
thead { display: table-header-group; }
tbody tr:nth-child(even) { background: #f6f8fa; }
 section { break-inside: avoid; }
 .interpretation { margin: 5pt 0 12pt; font-size: 8pt; color: #586c7a; }
 .alert-list { break-before: page; }
 .alerts { font-size: 7pt; }
 .alerts th, .alerts td { padding: 5pt 4pt; }
 .alerts th:first-child { width: 29%; }
 .alerts th:last-child, .alerts td:last-child { width: 14%; }
.disclaimer { margin-top: 18pt; font-size: 8pt; color: #586c7a; }
</style></head>
<body><header><strong>BEC Guard</strong>
<h1>Reporte operativo</h1>
<p>Periodo: """
        + escape(report.period)
        + "</p><p>Generado: "
        + report.generated_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        + "</p></header>"
        + sections
        + '<p class="disclaimer">'
        + escape(DISCLAIMER)
        + "</p></body></html>"
    )


def pdf_bytes(report: OperationalReport) -> bytes:
    from weasyprint import HTML

    def deny_fetch(*_args, **_kwargs):
        raise ValueError("Report templates do not fetch external resources")

    return HTML(string=pdf_html(report), url_fetcher=deny_fetch).write_pdf()
