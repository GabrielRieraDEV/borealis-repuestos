"""Salida de tickets: impresora térmica ESC/POS por nombre de Windows, o PDF/texto de respaldo (RF-54).

Un error de impresión nunca revierte el documento: quien llama ya hizo COMMIT.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class PrintError(Exception):
    """La impresora no respondió. El mensaje es para la usuaria."""


def send_to_printer(printer_name: str, lines: list[str], cut: bool = True) -> None:
    """Imprime en la térmica (ESC/POS crudo por el spooler de Windows)."""
    if not printer_name.strip():
        raise PrintError("No hay impresora de tickets configurada (Configuración > Impresora).")
    try:
        from escpos.printer import Win32Raw

        printer = Win32Raw(printer_name)
        printer.open()
        try:
            printer.text("\n".join(lines) + "\n\n")
            if cut:
                printer.cut()
        finally:
            printer.close()
    except Exception as exc:  # pywin32 / escpos lanzan tipos variados
        log.warning("No se pudo imprimir en %r: %s", printer_name, exc)
        raise PrintError(f"La impresora «{printer_name}» no respondió. Revise que esté encendida y con papel.") from exc


def save_pdf(path: Path, lines: list[str], title: str = "") -> Path:
    """PDF del ancho del ticket (80 mm), letra de ancho fijo."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    font_size = 7  # 48 columnas de Courier caben en 72 mm útiles
    leading = 9
    width = 80 * mm
    margin = 4 * mm
    height = 2 * margin + leading * (len(lines) + 1)
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setTitle(title or path.stem)
    c.setFont("Courier", font_size)
    y = height - margin - leading
    for line in lines:
        c.drawString(margin, y, line)
        y -= leading
    c.showPage()
    c.save()
    return path


def save_text(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
