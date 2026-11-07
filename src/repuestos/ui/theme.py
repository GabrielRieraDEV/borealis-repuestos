"""Tema claro fijo: el programa se ve igual aunque Windows esté en modo oscuro."""

from __future__ import annotations

from importlib import resources

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication


def app_icon() -> QIcon:
    return QIcon(str(resources.files("repuestos.ui") / "repuestos.ico"))


def apply_theme(app: QApplication, large_font: bool = False) -> None:
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    p = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f3f3f3",
        QPalette.ColorRole.WindowText: "#1f1f1f",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f7f7f7",
        QPalette.ColorRole.Text: "#1f1f1f",
        QPalette.ColorRole.Button: "#e9e9e9",
        QPalette.ColorRole.ButtonText: "#1f1f1f",
        QPalette.ColorRole.Highlight: "#1565c0",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#ffffe1",
        QPalette.ColorRole.ToolTipText: "#1f1f1f",
        QPalette.ColorRole.PlaceholderText: "#8a8a8a",
        QPalette.ColorRole.Link: "#1565c0",
    }
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#a0a0a0"))
    app.setPalette(p)
    font = app.font()
    font.setPointSize(14 if large_font else 11)
    app.setFont(font)
