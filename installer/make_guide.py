"""Genera la guía rápida (una página) en docs/guia-rapida.md, docs/guia-rapida.pdf y dentro del programa.

Uso: python installer/make_guide.py      (el contenido vive aquí: una sola fuente para el .md y el PDF)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Frame, FrameBreak, KeepTogether, PageTemplate, Paragraph, Spacer
from reportlab.platypus.doctemplate import BaseDocTemplate

from repuestos.config import BRAND_LINE

ROOT = Path(__file__).resolve().parents[1]

TITLE = "Guía rápida · Borealis Repuestos"
SUBTITLE = "Romero Alfa 1 · Tenga esta hoja junto a la computadora"

# (título, [pasos]) — pasos en orden; las teclas van entre [corchetes]
SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Vender",
        [
            "En la pantalla principal pulse [F5] (Vender).",
            "Escanee el código de barras: el producto se agrega solo.",
            "O escriba palabras del nombre (ej. «pastilla bera») y [Enter]; elija con [↑] [↓] y [Enter].",
            "Escriba la cantidad y [Enter]. Para metros o litros use coma: 2,5.",
            "[F4] cambia la cantidad del renglón elegido · [Supr] lo quita · [F3] elige el cliente.",
            "[Esc] cancela la venta.",
        ],
    ),
    (
        "2. Cobrar y dar vuelto",
        [
            "Pulse [F9]. Elija la forma de pago: [F1] efectivo Bs · [F2] efectivo USD · [F3] punto · [F4] pago móvil.",
            "Escriba el monto y [Enter]. Con el monto vacío, [Enter] completa lo que falta.",
            "Si hay vuelto: escriba cuántos USD entrega (puede ser 0); el sistema dice el resto en Bs.",
            "Pulse [F9] para cobrar: sale la nota de entrega. Si la impresora falla, la venta queda guardada.",
            "Fiado: con un cliente que tenga fiado, [F6] manda a fiado lo que falta.",
        ],
    ),
    (
        "3. Abrir y cerrar la caja",
        [
            "Abrir: Caja → escriba el efectivo que hay en USD y en Bs → Abrir caja. Sin caja abierta no se vende.",
            "Salida de efectivo (pagos, gastos): Caja → Salida de efectivo, monto y motivo → Registrar.",
            "Cerrar: cuente el efectivo → Cerrar caja… → escriba lo contado en USD y Bs.",
            "Sale el ticket de cierre y se hace un respaldo. Solo la dueña ve lo esperado y la diferencia.",
        ],
    ),
    (
        "4. Registrar una compra (dueña)",
        [
            "Compras → [Ctrl+N]. Elija el proveedor (o «Nuevo proveedor…»), la factura y la fecha.",
            "Producto [Enter] → cantidad [Enter] → costo unitario USD [Enter] para agregar el renglón.",
            "Si viene por caja o docena: [F4] «Por empaque» calcula unidades y costo.",
            "[Ctrl+S] guarda: suben las existencias y se actualiza el costo promedio.",
        ],
    ),
    (
        "5. Ver qué pedir (dueña)",
        [
            "La pantalla principal avisa «Para pedir: N productos» → Ver la lista.",
            "O Inventario → Para pedir: por categoría, con el último proveedor y costo.",
            "Para imprimirla: Reportes → Para pedir → Ver → Imprimir.",
        ],
    ),
    (
        "6. Registrar un abono de fiado",
        [
            "Fiado → Deudores → elija el cliente → Registrar abono (la caja debe estar abierta).",
            "Elija la forma de pago y el monto: el sistema muestra cuánto abona en USD y cómo queda el saldo.",
            "Guardar abono: sale el comprobante AB-…; se aplica a la deuda más vieja primero.",
        ],
    ),
]

TIPS = [
    "La tasa BCV se descarga sola. Si dice «sin tasa»: Tasa BCV → Cargar a mano.",
    "El respaldo es automático (al abrir, al cerrar caja y al salir) y se copia a Google Drive.",
    "¿Dudas? Escriba a Borealis por WhatsApp. Nunca borre la carpeta C:\\ProgramData\\BorealisRepuestos.",
]


def _keys_html(text: str) -> str:
    return text.replace("[", "<font face='Helvetica-Bold' color='#0d47a1'>[").replace("]", "]</font>")


def write_markdown(path: Path) -> None:
    lines = [f"# {TITLE}", "", f"_{SUBTITLE}_", ""]
    for title, steps in SECTIONS:
        lines += [f"## {title}", ""]
        lines += [f"{i}. {step.replace('[', '**[').replace(']', ']**')}" for i, step in enumerate(steps, 1)]
        lines.append("")
    lines += ["## Bueno saber", ""] + [f"- {t}" for t in TIPS] + [""]
    lines += ["<!-- Generado por installer/make_guide.py: edite ahí y vuelva a correrlo. -->", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_pdf(path: Path) -> None:
    title = ParagraphStyle(
        "t", fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=colors.HexColor("#0d47a1")
    )
    sub = ParagraphStyle("s", fontName="Helvetica", fontSize=10, leading=12, textColor=colors.HexColor("#555555"))
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=8, spaceAfter=3)
    step = ParagraphStyle("p", fontName="Helvetica", fontSize=10.6, leading=13.4, leftIndent=11, firstLineIndent=-11)
    margin = 12 * mm
    width, height = letter
    header_h = 20 * mm
    col_w = (width - 2 * margin - 6 * mm) / 2
    body_h = height - 2 * margin - header_h
    frames = [
        Frame(margin, height - margin - header_h, width - 2 * margin, header_h, id="head", showBoundary=0),
        Frame(margin, margin, col_w, body_h, id="c1", showBoundary=0),
        Frame(margin + col_w + 6 * mm, margin, col_w, body_h, id="c2", showBoundary=0),
    ]
    doc = BaseDocTemplate(str(path), pagesize=letter, title=TITLE, author="Borealis Software Solutions")

    def footer(canvas, _doc) -> None:
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6b7a90"))
        canvas.drawCentredString(width / 2, 7 * mm, f"Borealis Repuestos · {BRAND_LINE}")

    doc.addPageTemplates([PageTemplate(id="una", frames=frames, onPage=footer)])
    story = [Paragraph(TITLE, title), Paragraph(SUBTITLE, sub)]
    story.append(FrameBreak())
    for n, (title_text, steps) in enumerate(SECTIONS):
        if n == 3:
            story.append(FrameBreak())  # columna derecha: compras, para pedir, abonos y consejos
        block = [Paragraph(title_text, h)]
        block += [Paragraph(f"{i}. {_keys_html(s)}", step) for i, s in enumerate(steps, 1)]
        story.append(KeepTogether(block))
    story.append(Spacer(1, 3 * mm))
    tips = [Paragraph("Bueno saber", h)] + [Paragraph(f"• {_keys_html(t)}", step) for t in TIPS]
    story.append(KeepTogether(tips))
    doc.build(story)


def main() -> None:
    docs = ROOT / "docs"
    write_markdown(docs / "guia-rapida.md")
    pdf = docs / "guia-rapida.pdf"
    write_pdf(pdf)
    shutil.copyfile(pdf, ROOT / "src" / "repuestos" / "ui" / "guia-rapida.pdf")
    print(f"Guía escrita en {docs}")


if __name__ == "__main__":
    main()
