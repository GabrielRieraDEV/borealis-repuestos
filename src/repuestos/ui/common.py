"""Utilidades de la interfaz: mensajes de error claros y campos numéricos."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLineEdit, QMessageBox, QWidget

from repuestos.domain.money import hu
from repuestos.ui.formatting import format_number, parse_decimal

#: Errores "de negocio": su mensaje ya está escrito para la usuaria.
USER_ERRORS = (ValueError, PermissionError, LookupError)


def run_action[T](parent: QWidget | None, action: Callable[[], T], title: str = "No se pudo guardar") -> T | None:
    """Ejecuta una acción del servicio. Los errores de negocio se muestran; los demás van al log (excepthook)."""
    try:
        return action()
    except USER_ERRORS as exc:
        QMessageBox.warning(parent, title, str(exc))
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            QMessageBox.warning(parent, title, "La base de datos está ocupada. Intente de nuevo en unos segundos.")
        else:
            raise
    return None


def decimal_field_text(value: Decimal, decimals: int, strip: bool = False) -> str:
    """Texto para un campo editable: '12,50' (sin 'Bs'/'USD'). Con ``strip`` quita ceros sobrantes ('2,5')."""
    text = format_number(hu(value, decimals), decimals)
    if strip and "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def read_decimal(field: QLineEdit, label: str, default: Decimal | None = None) -> Decimal:
    text = field.text().strip()
    if not text and default is not None:
        return default
    try:
        return parse_decimal(text)
    except ValueError:
        field.setFocus()
        field.selectAll()
        raise ValueError(f"{label}: escriba un número, por ejemplo 12,50.") from None


def format_qty(value: Decimal, allows_fraction: bool) -> str:
    return decimal_field_text(value, 3, strip=True) if allows_fraction else format_number(value, 0)


class EnterMovesFocusDialog(QDialog):
    """Enter pasa al campo siguiente en vez de cerrar el diálogo (el lector de códigos termina en Enter)."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        ):
            self.focusNextChild()
            return
        super().keyPressEvent(event)
