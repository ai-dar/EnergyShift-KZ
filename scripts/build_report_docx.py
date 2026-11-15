"""Конвертация docs/REPORT.md в docs/REPORT.docx (python-docx): заголовки, абзацы, списки, таблицы, рисунки."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "REPORT.md"
OUT = ROOT / "docs" / "REPORT.docx"
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")


def add_runs(paragraph, text: str, size: float | None = None, bold: bool = False) -> None:
    """Добавить текст с разметкой **жирный**, *курсив*, `код`."""
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2]); run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1]); run.font.name = "Consolas"; run.font.size = Pt((size or 11) - 1)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            run = paragraph.add_run(part[1:-1]); run.italic = True
        else:
            run = paragraph.add_run(part)
        if size:
            run.font.size = Pt(size)
        if bold:
            run.bold = True


def set_cell_shading(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def add_table(doc: Document, rows: list[list[str]]) -> None:
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        add_runs(cell.paragraphs[0], text, size=9, bold=True)
        set_cell_shading(cell, "DCE6F1")
    for row in body:
        cells = table.add_row().cells
        for i, text in enumerate(row[:len(header)]):
            cells[i].text = ""
            add_runs(cells[i].paragraphs[0], text, size=9)
    doc.add_paragraph()


def add_image(doc: Document, caption: str, path: Path) -> None:
    if not path.exists():
        doc.add_paragraph(f"[рисунок не найден: {path.name}]")
        return
    doc.add_picture(str(path), width=Cm(16))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run(caption); run.italic = True; run.font.size = Pt(9.5); run.font.color.rgb = RGBColor(0x40, 0x40, 0x40)


def build() -> Path:
    doc = Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2.0)
        section.top_margin = section.bottom_margin = Cm(2.0)
    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(11)
    styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    styles["Normal"].paragraph_format.space_after = Pt(6)
    for name, size in (("Title", 22), ("Heading 1", 16), ("Heading 2", 13)):
        st = styles[name]
        st.font.name = "Calibri"; st.font.size = Pt(size); st.font.bold = True
        st.font.color.rgb = RGBColor(0x1F, 0x3B, 0x63)
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        st.paragraph_format.space_before = Pt(14 if name != "Title" else 0)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True

    lines = SRC.read_text(encoding="utf-8").splitlines()
    i, table_rows, title_done = 0, [], False
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not re.match(r"^\|?\s*:?-{2,}", line):
                table_rows.append(cells)
            i += 1
            if i >= len(lines) or not lines[i].startswith("|"):
                add_table(doc, table_rows); table_rows = []
            continue
        if line.startswith("# "):
            p = doc.add_paragraph(line[2:], style="Title"); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            # строки после заголовка до пустой — подзаголовок титульной части
            while i < len(lines) and lines[i].strip():
                sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_runs(sub, lines[i].strip(), size=11)
                i += 1
            continue
        if line.startswith("## "):
            doc.add_heading(line[3:], level=1); i += 1; continue
        if line.startswith("### "):
            doc.add_heading(line[4:], level=2); i += 1; continue
        m = re.match(r"!\[(.*?)\]\((.*?)\)", line)
        if m:
            add_image(doc, m.group(1), (SRC.parent / m.group(2)).resolve()); i += 1; continue
        if line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet"); add_runs(p, line[2:]); i += 1; continue
        m = re.match(r"^(\d+)\. (.*)", line)
        if m:
            p = doc.add_paragraph(style="List Number"); add_runs(p, m.group(2)); i += 1; continue
        if not line.strip():
            i += 1; continue
        # абзац: склеиваем последовательные непустые строки без спецсимволов
        buf = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||!\[|- |\d+\. )", lines[i]):
            buf.append(lines[i].strip()); i += 1
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_runs(p, " ".join(buf))
    doc.core_properties.title = "EnergyShift KZ: Global Energy Mix and CO₂ Emissions"
    doc.core_properties.author = "Aidar, Daniyal, Nurzhan (AAI-2604)"
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print("written", build())
