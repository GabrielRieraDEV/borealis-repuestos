"""Diálogo reutilizable "Autorizar con clave de la dueña" (RF-04)."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from repuestos.domain.users import User
from repuestos.services import user_service


class AuthorizeDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, requested_by: User, action: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._requested_by = requested_by
        self._action = action
        self.owner_id: int | None = None
        self.setWindowTitle("Autorizar con clave de la dueña")

        text = QLabel(f"Para <b>{action}</b> hace falta la autorización de la dueña.<br>Escriba su clave:")
        text.setWordWrap(True)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._error = QLabel()
        self._error.setStyleSheet("color: #b00020;")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Autorizar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(self._password)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    def _check(self) -> None:
        owner_id = user_service.authorize_owner(self._conn, self._password.text(), self._requested_by, self._action)
        if owner_id is None:
            self._error.setText("Clave incorrecta.")
            self._password.clear()
            self._password.setFocus()
            return
        self.owner_id = owner_id
        self.accept()


def ask_owner_authorization(
    conn: sqlite3.Connection, requested_by: User, action: str, parent: QWidget | None = None
) -> int | None:
    """Devuelve el id de la dueña que autorizó, o None si se canceló.

    Si quien pide ya es la dueña, se autoriza sin preguntar.
    """
    if requested_by.is_owner:
        return requested_by.id
    dialog = AuthorizeDialog(conn, requested_by, action, parent)
    return dialog.owner_id if dialog.exec() == QDialog.DialogCode.Accepted else None
