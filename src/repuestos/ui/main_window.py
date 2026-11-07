"""Ventana principal (Fase 0: vacía, con la barra de estado)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

from repuestos.domain.users import ROLE_LABELS, User


class MainWindow(QMainWindow):
    def __init__(self, user: User, business_name: str) -> None:
        super().__init__()
        self.user = user
        self.setWindowTitle(f"{business_name or 'Borealis Repuestos'} — Inventario, ventas y caja")
        self.resize(1200, 720)

        welcome = QLabel(f"Bienvenido(a), {user.full_name}")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet("font-size: 20pt;")
        self.setCentralWidget(welcome)

        bar = self.statusBar()
        self.user_label = QLabel(f"Usuario: {user.full_name} ({ROLE_LABELS[user.role]})")
        self.rate_label = QLabel("Tasa: sin tasa")
        self.cash_label = QLabel("Caja: cerrada")
        self.backup_label = QLabel("Respaldo: nunca")
        for label in (self.user_label, self.rate_label, self.cash_label, self.backup_label):
            label.setContentsMargins(8, 0, 8, 0)
            bar.addPermanentWidget(label)
