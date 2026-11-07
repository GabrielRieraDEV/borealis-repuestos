"""Imprimir con alternativa: si la impresora falla, reintentar, guardar PDF o seguir (RF-54).

El documento ya está guardado: un error de impresión nunca lo revierte.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from repuestos.printing.printer import PrintError

log = logging.getLogger(__name__)


def print_with_fallback(parent: QWidget | None, do_print: Callable[[], None], save_pdf: Callable[[], Path]) -> bool:
    """Devuelve True si se imprimió o se guardó el PDF."""
    while True:
        try:
            do_print()
            return True
        except PrintError as exc:
            box = QMessageBox(parent)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("No se pudo imprimir")
            box.setText(f"{exc}\n\nEl documento quedó guardado. ¿Qué desea hacer?")
            retry = box.addButton("Reintentar", QMessageBox.ButtonRole.AcceptRole)
            pdf = box.addButton("Guardar PDF", QMessageBox.ButtonRole.ActionRole)
            box.addButton("Seguir sin imprimir", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is retry:
                continue
            if box.clickedButton() is pdf:
                return save_and_open_pdf(parent, save_pdf)
            return False


def save_and_open_pdf(parent: QWidget | None, save_pdf: Callable[[], Path]) -> bool:
    try:
        path = save_pdf()
    except OSError:
        log.exception("No se pudo guardar el PDF")
        QMessageBox.warning(
            parent,
            "PDF",
            "No se pudo guardar el PDF. Cierre el PDF si está abierto en otro programa e intente de nuevo.",
        )
        return False
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # abre el visor de PDF de Windows
    except (AttributeError, OSError):
        QMessageBox.information(parent, "PDF guardado", f"Se guardó en:\n{path}")
    return True
