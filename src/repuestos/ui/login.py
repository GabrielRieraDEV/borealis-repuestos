"""Ventana de inicio de sesión (RF-01)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from repuestos.domain.users import User
from repuestos.services import auth_service
from repuestos.ui.brand import brand_label, test_mode_banner


class LoginDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, business_name: str, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self.user: User | None = None
        self.setWindowTitle("Iniciar sesión")
        self.setMinimumWidth(380)

        title = QLabel(business_name or "Borealis Repuestos")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self._username = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._error = QLabel()
        self._error.setStyleSheet("color: #b00020;")
        self._error.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Usuario:", self._username)
        form.addRow("Contraseña:", self._password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Entrar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Salir")
        buttons.accepted.connect(self._try_login)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        banner = test_mode_banner()
        if banner is not None:
            layout.addWidget(banner)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(buttons)
        layout.addWidget(brand_label(), 0, Qt.AlignmentFlag.AlignRight)
        self._username.setFocus()

    def _try_login(self) -> None:
        try:
            self.user = auth_service.login(self._conn, self._username.text(), self._password.text())
        except auth_service.AuthError as exc:
            self._error.setText(str(exc))
            self._password.clear()
            self._password.setFocus()
            return
        self.accept()
