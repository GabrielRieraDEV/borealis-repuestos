"""Marca de Borealis y aviso de modo de prueba, reutilizables en las ventanas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from repuestos.config import BRAND_LINE, is_test_mode

TEST_STYLE = "background: #ffd54f; color: #3e2700; font-weight: bold; padding: 6px; border-radius: 4px;"


def brand_label() -> QLabel:
    label = QLabel(BRAND_LINE)
    label.setStyleSheet("color: #6b7a90; font-size: 9pt;")
    return label


def test_mode_banner() -> QLabel | None:
    """Banda amarilla en modo de prueba; None en el uso normal."""
    if not is_test_mode():
        return None
    label = QLabel("MODO DE PRUEBA · estos datos son de práctica, no son los del negocio")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(TEST_STYLE)
    return label
