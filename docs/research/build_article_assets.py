"""Dibuja las cinco figuras de datos del manuscrito usando evidencia local agregada."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "artifacts/research/training_v1/article_evidence.json"
REPORT = ROOT / "artifacts/research/training_v1/model/training_report.json"
OUT = Path(__file__).resolve().parent / "figures"
INK = "#16324a"
TEAL = "#087a82"
BLUE = "#347ca8"
ORANGE = "#db773f"
GRAY = "#586b79"
PALE = "#eaf4f5"
BG = "#ffffff"


def font(size: int, *, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def canvas(title: str, subtitle: str):
    image = Image.new("RGB", (1600, 950), BG)
    draw = ImageDraw.Draw(image)
    draw.text((75, 48), title, font=font(44, bold=True), fill=INK)
    draw.text((78, 110), subtitle, font=font(24), fill=GRAY)
    draw.line((75, 156, 1525, 156), fill="#d3e4e7", width=3)
    return image, draw


def centre(draw, x: int, y: int, text: str, size=27, color=INK, bold=False):
    box = draw.textbbox((0, 0), text, font=font(size, bold=bold))
    draw.text((x - (box[2] - box[0]) / 2, y), text, font=font(size, bold=bold), fill=color)


def box(draw, bounds, title, detail, fill=PALE):
    draw.rounded_rectangle(bounds, radius=22, fill=fill, outline="#a3c7cb", width=3)
    x = (bounds[0] + bounds[2]) // 2
    centre(draw, x, bounds[1] + 28, title, 28, bold=True)
    centre(draw, x, bounds[1] + 75, detail, 20, color=GRAY)


def arrow(draw, start, end):
    draw.line((*start, *end), fill=TEAL, width=6)
    x, y = end
    if end[0] > start[0]:
        draw.polygon([(x, y), (x - 17, y - 11), (x - 17, y + 11)], fill=TEAL)
    else:
        draw.polygon([(x, y), (x - 11, y - 17), (x + 11, y - 17)], fill=TEAL)


def architecture():
    im, d = canvas("Arquitectura evaluada", "Del correo ficticio al score y a la alerta persistida")
    box(d, (75, 327, 345, 447), "Entrada HTTP", "Asunto + cuerpo")
    box(d, (435, 205, 735, 325), "Reglas", "Contexto · det-v3")
    box(d, (435, 400, 735, 520), "Modelo TF-IDF", "Umbral 0,5 · SHA-256", "#fff2e8")
    box(d, (435, 595, 735, 715), "Semántica", "Opcional; sin ejecución", "#f2f4f6")
    box(d, (832, 327, 1130, 447), "Fusión", "shadow / assist")
    box(d, (1230, 205, 1520, 325), "Alerta", "Score final >= 50", "#fff2e8")
    box(d, (1230, 522, 1520, 642), "PostgreSQL", "Análisis y trazabilidad")
    for end in ((435, 265), (435, 460), (435, 655)):
        arrow(d, (345, 387), end)
    for start in ((735, 265), (735, 460), (735, 655)):
        arrow(d, start, (832, 387))
    arrow(d, (1130, 387), (1230, 265))
    arrow(d, (1130, 387), (1230, 582))
    centre(d, 800, 830, "El modelo no recibió etiquetas, remitentes ni IDs como variables.", 23)
    im.save(OUT / "figura01_arquitectura.png")


def composition(evidence):
    im, d = canvas(
        "Composición del corpus sintético", "Separación por grupos; 500 mensajes, 250 grupos de dos"
    )
    counts = evidence["split_counts"]
    for x, name in zip((335, 800, 1265), ("train", "validation", "test"), strict=True):
        values = counts[name]
        leg, bec = values["LEGITIMATE"], values["BEC"]
        h1, h2 = round(510 * leg / 350), round(510 * bec / 350)
        bottom = 750
        d.rounded_rectangle((x - 115, bottom - h1, x + 115, bottom), radius=8, fill=BLUE)
        d.rectangle((x - 115, bottom - h1 - h2, x + 115, bottom - h1), fill=ORANGE)
        centre(d, x, bottom - h1 / 2 - 14, str(leg), 33, BG, bold=True)
        if h2 >= 60:
            centre(d, x, bottom - h1 - h2 / 2 - 14, str(bec), 31, BG, bold=True)
        else:
            centre(d, x, bottom - h1 - h2 - 40, f"BEC {bec}", 24, color=ORANGE, bold=True)
        centre(d, x, 779, f"{name.upper()} · n={leg + bec}", 26, bold=True)
    d.rectangle((456, 860, 487, 891), fill=BLUE)
    d.text((500, 857), "Legítimos (380)", font=font(24), fill=INK)
    d.rectangle((835, 860, 866, 891), fill=ORANGE)
    d.text((879, 857), "BEC (120)", font=font(24), fill=INK)
    im.save(OUT / "figura02_corpus.png")


def thresholds(report):
    im, d = canvas(
        "Selección de umbral en validación",
        "FPR calculado sobre 58 legítimos; 18/18 BEC identificados en cada umbral",
    )
    values = report["validation"]
    axis_y, scale = 760, 490 / 10
    d.line((230, axis_y, 1450, axis_y), fill=INK, width=3)
    goal = axis_y - 5 * scale
    d.line((230, goal, 1450, goal), fill=ORANGE, width=3)
    d.text((1090, goal - 38), "Objetivo FPR: 5 %", font=font(23, bold=True), fill=ORANGE)
    for x, key in zip((400, 800, 1200), ("0.4", "0.5", "0.6"), strict=True):
        rate = values[key]["fpr"] * 100
        height = round(rate * scale)
        d.rounded_rectangle((x - 85, axis_y - height, x + 85, axis_y), radius=9, fill=TEAL)
        centre(d, x, axis_y - height - 60, f"{rate:.1f} %", 30, bold=True)
        centre(d, x, 790, f"Umbral {key}", 27, bold=True)
        centre(d, x, 838, f"FP {values[key]['fp']}; TP {values[key]['tp']}", 23)
    im.save(OUT / "figura03_umbral.png")


def confusion(evidence):
    im, d = canvas(
        "Matrices de confusión en el test sintético",
        "18 BEC y 56 legítimos; decisión de alerta operativa",
    )
    labels = (
        ("majority_baseline", "Mayoría legítima"),
        ("rules_C1", "Reglas C1"),
        ("trained_model", "TF-IDF"),
        ("rules_plus_model_assist", "Reglas + modelo"),
    )
    for index, (key, title) in enumerate(labels):
        x = 75 + (index % 2) * 760
        y = 195 + (index // 2) * 360
        r = evidence["test_results"][key]
        centre(d, x + 345, y, title, 29, bold=True)
        for row, col, value, tag in (
            (0, 0, r["tn"], "TN"),
            (0, 1, r["fp"], "FP"),
            (1, 0, r["fn"], "FN"),
            (1, 1, r["tp"], "TP"),
        ):
            left = x + 100 + 240 * col
            top = y + 58 + 115 * row
            fill = "#e9f5f2" if tag in ("TN", "TP") else "#fff0e5"
            d.rounded_rectangle((left, top, left + 215, top + 103), radius=12, fill=fill)
            centre(d, left + 107, top + 11, f"{tag}: {value}", 31, bold=True)
            centre(d, left + 107, top + 57, "BEC" if col else "Legítimo", 19, color=GRAY)
        centre(
            d,
            x + 345,
            y + 298,
            "Filas: verdad legítima / BEC · columnas: predicción",
            19,
            color=GRAY,
        )
    im.save(OUT / "figura04_matrices.png")


def rates(evidence):
    im, d = canvas(
        "Sensibilidad y falsas alertas",
        "Tasas descriptivas del mismo test sintético; no generalizables",
    )
    labels = (
        ("majority_baseline", "Mayoría"),
        ("rules_C1", "Reglas"),
        ("trained_model", "TF-IDF"),
        ("rules_plus_model_assist", "Assist"),
    )
    axis_y = 740
    d.line((120, axis_y, 1510, axis_y), fill=INK, width=3)
    goal = axis_y - 4.6 * 5
    d.line((120, goal, 1510, goal), fill=ORANGE, width=2)
    d.text((122, goal - 31), "FPR objetivo = 5 %", font=font(21), fill=ORANGE)
    for x, (key, label) in zip((285, 630, 975, 1320), labels, strict=True):
        row = evidence["test_results"][key]
        for dx, field, color in ((-56, "recall", TEAL), (56, "fpr", ORANGE)):
            percent = row[field] * 100
            height = int(percent * 4.6)
            if height:
                d.rectangle((x + dx - 48, axis_y - height, x + dx + 48, axis_y), fill=color)
            centre(d, x + dx, axis_y - height - 37, f"{percent:.1f}", 23, bold=True)
        centre(d, x, 770, label, 25, bold=True)
    d.rectangle((455, 863, 482, 890), fill=TEAL)
    d.text((495, 861), "Recall (18 BEC)", font=font(22), fill=INK)
    d.rectangle((820, 863, 847, 890), fill=ORANGE)
    d.text((860, 861), "FPR (56 legítimos)", font=font(22), fill=INK)
    im.save(OUT / "figura05_tasas.png")


def main():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if evidence["status"] != "SYNTHETIC_FIXTURE_REUSE_DESCRIPTIVE_ONLY":
        raise ValueError("Se requieren agregados del fixture identificado")
    if evidence["dataset_sha256"] != report["dataset_sha256"]:
        raise ValueError("Los resultados no corresponden al modelo")
    if not OUT.is_dir():
        raise ValueError("Falta el directorio de figuras")
    architecture()
    composition(evidence)
    thresholds(report)
    confusion(evidence)
    rates(evidence)
    print("Cinco figuras PNG regeneradas desde evidencias locales")


if __name__ == "__main__":
    main()
