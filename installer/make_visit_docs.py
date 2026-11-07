"""Convierte docs/visita/*.md en PDF para imprimir (uno por documento + la carpeta completa).

Uso: python installer/make_visit_docs.py
Soporta lo que usan esos documentos: títulos, párrafos, listas, casillas, tablas, citas, **negrita** y `código`.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from repuestos.config import BRAND
from repuestos.printing.reports import _NumberedCanvas

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "visita"
BLUE = colors.HexColor("#0d47a1")

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=BLUE, spaceAfter=6)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=4)
ITEM = ParagraphStyle("i", parent=BODY, leftIndent=14, firstLineIndent=-10, spaceAfter=2)
SUB = ParagraphStyle("s", parent=ITEM, leftIndent=28)
QUOTE = ParagraphStyle("q", parent=BODY, leftIndent=8, textColor=colors.HexColor("#5d4037"), backColor="#fff8e1",
                       borderPadding=5, spaceBefore=4, spaceAfter=8)  # fmt: skip
CELL = ParagraphStyle("c", fontName="Helvetica", fontSize=9, leading=11.5)
CELL_H = ParagraphStyle("ch", parent=CELL, fontName="Helvetica-Bold")
_SYMBOLS = Path(r"C:\Windows\Fonts\seguisym.ttf")
if _SYMBOLS.exists():  # casilla vacía ☐ para marcar a mano
    pdfmetrics.registerFont(TTFont("Simbolos", str(_SYMBOLS)))
    BOX_GLYPH = "<font name='Simbolos' size='12'>☐</font>"
else:
    BOX_GLYPH = "<font name='Courier-Bold'>[&nbsp;&nbsp;]</font>"
BOX = BOX_GLYPH + "&nbsp;&nbsp;"


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = t.replace("☐", BOX_GLYPH)  # casillas dentro del texto (ej. el acta)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<font name='Courier' size='9'>\1</font>", t)
    t = re.sub(r"(?<![\w*])_(.+?)_(?![\w*])", r"<i>\1</i>", t)
    return t


def _table(rows: list[list[str]], width: float) -> Table:
    n = len(rows[0])
    weights = [max(len(r[i]) for r in rows) for i in range(n)]
    weights = [min(max(w, 8), 70) for w in weights]
    total = sum(weights)
    data = [[Paragraph(inline(c), CELL_H if r == 0 else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[width * w / total for w in weights], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                ("GRID", (0, 0), (-1, -1), mm / 5, colors.HexColor("#b0b0b0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def parse(md: str, width: float) -> list[Flowable]:
    out: list[Flowable] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            out += [_table(rows, width), Spacer(1, 3 * mm)]
            continue
        if line.startswith("# "):
            out.append(Paragraph(inline(line[2:]), H1))
        elif line.startswith("## "):
            out.append(Paragraph(inline(line[3:]), H2))
        elif line.startswith("### "):
            out.append(Paragraph(inline(line[4:]), H3))
        elif line.strip() == "---":
            out.append(Spacer(1, 4 * mm))
        elif line.startswith("> "):
            out.append(Paragraph(inline(line[2:]), QUOTE))
        else:
            m = re.match(r"^(\s*)(- \[ \] |- |\d+\. )(.*)$", line)
            text = m.group(3) if m else line
            # líneas siguientes con sangría continúan el mismo renglón
            while (
                i + 1 < len(lines) and lines[i + 1].startswith("  ") and not re.match(r"^\s*(- |\d+\. )", lines[i + 1])
            ):
                i += 1
                text += " " + lines[i].strip()
            if not m:  # párrafo: se juntan las líneas seguidas hasta una línea vacía o un bloque nuevo
                while (
                    i + 1 < len(lines)
                    and lines[i + 1].strip()
                    and not re.match(r"^(\s*(- |\d+\. )|#|\||>|---)", lines[i + 1])
                ):
                    i += 1
                    text += " " + lines[i].strip()
            if m:
                indent, marker = m.group(1), m.group(2)
                style = SUB if indent else ITEM
                bullet = BOX if marker.startswith("- [ ]") else ("•&nbsp;&nbsp;" if marker == "- " else marker)
                out.append(Paragraph(bullet + inline(text), style))
            else:
                out.append(Paragraph(inline(text), BODY))
        i += 1
    return out


def _doc(path: Path, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path), pagesize=letter, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=18 * mm,
        title=title, author=BRAND,
    )  # fmt: skip


def main() -> None:
    width = letter[0] - 32 * mm
    sources = sorted(SRC.glob("*.md"))
    combined: list[Flowable] = [
        Paragraph("Visita de instalación · Romero Alfa 1", H1),
        Paragraph(f"Carpeta para Josner · {BRAND}", BODY),
        Spacer(1, 6 * mm),
    ]
    combined += [
        Paragraph("•&nbsp;&nbsp;" + inline(p.stem.replace("-", " ", 1).replace("-", " ")), ITEM) for p in sources
    ]
    for src in sources:
        text = src.read_text(encoding="utf-8")
        _doc(src.with_suffix(".pdf"), src.stem).build(parse(text, width), canvasmaker=_NumberedCanvas)
        combined += [PageBreak(), *parse(text, width)]  # bloques nuevos: reportlab consume los que ya usó
        print(f"PDF: {src.with_suffix('.pdf').name}")
    _doc(SRC / "carpeta-de-la-visita.pdf", "Carpeta de la visita").build(
        [KeepTogether(combined[:4]), *combined[4:]], canvasmaker=_NumberedCanvas
    )
    print("PDF: carpeta-de-la-visita.pdf")


if __name__ == "__main__":
    main()
