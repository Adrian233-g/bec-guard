from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "research" / "ARTICULO_BEC_GUARD_Q1.md"
TARGET = ROOT / "docs" / "research" / "ARTICULO_BEC_GUARD_Q1_ACTUALIZADO.docx"

BODY_FONT = "Times New Roman"
MONO_FONT = "Consolas"

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*]+?\*)")


def set_run_font(run, name: str = BODY_FONT, size: float | None = None) -> None:
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attribute), name)
    if size is not None:
        run.font.size = Pt(size)


def add_runs(paragraph: Paragraph, text: str, size: float = 12) -> None:
    for token in INLINE.split(text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
            set_run_font(run, size=size)
        elif token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, name=MONO_FONT, size=size - 1)
        elif token.startswith("*") and token.endswith("*") and len(token) > 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
            set_run_font(run, size=size)
        else:
            run = paragraph.add_run(token)
            set_run_font(run, size=size)


def add_page_number(paragraph: Paragraph) -> None:
    run = paragraph.add_run()
    fld_begin = run._element.makeelement(qn("w:fldChar"), {})
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = run._element.makeelement(qn("w:instrText"), {})
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = run._element.makeelement(qn("w:fldChar"), {})
    fld_end.set(qn("w:fldCharType"), "end")
    run._element.append(fld_begin)
    run._element.append(instr)
    run._element.append(fld_end)
    set_run_font(run, size=11)


def parse_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [cell.strip() for cell in cells]


def is_separator(line: str) -> bool:
    cells = parse_row(line)
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def alignment_for(cell: str):
    cell = cell.strip()
    if cell.startswith(":") and cell.endswith(":"):
        return WD_ALIGN_PARAGRAPH.CENTER
    if cell.endswith(":"):
        return WD_ALIGN_PARAGRAPH.RIGHT
    return WD_ALIGN_PARAGRAPH.LEFT


def build(target: Path = TARGET) -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    document = Document()

    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for name, size in (("Heading 1", 14), ("Heading 2", 12.5)):
        style = document.styles[name]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.space_before = Pt(14)
        style.paragraph_format.space_after = Pt(8)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_number(footer)

    index = 0
    in_references = False
    in_bullets = False

    def blank_or_special(line: str) -> bool:
        return not line.strip()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if blank_or_special(line):
            index += 1
            continue

        if stripped.startswith("# "):
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_after = Pt(18)
            run = paragraph.add_run(stripped[2:].strip())
            run.bold = True
            set_run_font(run, size=17)
            index += 1
            continue

        if stripped.startswith("## "):
            title = stripped[3:].strip()
            in_references = title.lower().startswith("referencias")
            in_bullets = False
            document.add_heading(title, level=1)
            index += 1
            continue

        if stripped.startswith("### "):
            in_bullets = False
            document.add_heading(stripped[4:].strip(), level=2)
            index += 1
            continue

        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image_match:
            path = (SOURCE.parent / image_match.group(2)).resolve()
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(10)
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.add_run().add_picture(str(path), width=Cm(15.5))
            index += 1
            continue

        if stripped.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index].strip())
                index += 1
            if len(block) >= 2 and is_separator(block[1]):
                header = parse_row(block[0])
                aligns = [alignment_for(cell) for cell in parse_row(block[1])]
                body = [parse_row(row) for row in block[2:]]
                table = document.add_table(rows=1, cols=len(header))
                table.style = "Table Grid"
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.autofit = True
                for position, text in enumerate(header):
                    cell = table.rows[0].cells[position]
                    cell.paragraphs[0].alignment = aligns[position]
                    cell.paragraphs[0].paragraph_format.line_spacing_rule = (
                        WD_LINE_SPACING.SINGLE
                    )
                    cell.paragraphs[0].paragraph_format.space_after = Pt(2)
                    add_runs(cell.paragraphs[0], text, size=9)
                    for run in cell.paragraphs[0].runs:
                        run.bold = True
                for row in body:
                    cells = table.add_row().cells
                    for position, text in enumerate(row):
                        cells[position].paragraphs[0].alignment = aligns[position]
                        cells[position].paragraphs[
                            0
                        ].paragraph_format.line_spacing_rule = (
                            WD_LINE_SPACING.SINGLE
                        )
                        cells[position].paragraphs[0].paragraph_format.space_after = Pt(
                            2
                        )
                        add_runs(cells[position].paragraphs[0], text, size=9)
                document.add_paragraph().paragraph_format.space_after = Pt(2)
                in_bullets = False
            continue

        if stripped.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            add_runs(paragraph, stripped[2:], size=11)
            in_bullets = True
            index += 1
            continue

        caption_match = re.match(r"\*\*(Tabla|Figura) (\d+)\.\*\*\s*(.*)", stripped)
        if caption_match:
            paragraph = document.add_paragraph()
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER
                if caption_match.group(1) == "Figura"
                else WD_ALIGN_PARAGRAPH.LEFT
            )
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.paragraph_format.space_before = Pt(4)
            paragraph.paragraph_format.space_after = Pt(10)
            label = f"{caption_match.group(1)} {caption_match.group(2)}."
            run = paragraph.add_run(label + " ")
            run.bold = True
            set_run_font(run, size=10)
            add_runs(paragraph, caption_match.group(3), size=10)
            index += 1
            continue

        paragraph = document.add_paragraph()
        if stripped.startswith("**Tipo de contribución:**"):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            add_runs(paragraph, stripped, size=11)
            for run in paragraph.runs:
                run.italic = True
        elif in_references:
            paragraph.paragraph_format.first_line_indent = Cm(-1.25)
            paragraph.paragraph_format.left_indent = Cm(1.25)
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            add_runs(paragraph, stripped, size=11)
        else:
            add_runs(paragraph, stripped)
        index += 1

    document.core_properties.title = (
        "Del laboratorio a la alerta: integración auditable de un clasificador "
        "supervisado en un detector híbrido de fraude ejecutivo por correo "
        "electrónico"
    )
    document.core_properties.subject = "Artículo de investigación"
    document.core_properties.keywords = (
        "BEC; seguridad del correo; clasificación supervisada; datos sintéticos"
    )
    document.save(target)
    print(f"Escrito: {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construye el manuscrito Word desde Markdown")
    parser.add_argument("--output", type=Path, default=TARGET)
    build(parser.parse_args().output)
