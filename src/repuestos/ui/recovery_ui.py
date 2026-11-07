"""Código de recuperación de la clave de la dueña: mostrarlo una sola vez y usarlo si olvidó la clave."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from repuestos.services import recovery_service


class RecoveryCodeDialog(QDialog):
    """Muestra el código UNA vez. No se cierra hasta marcar «Ya lo anoté»."""

    def __init__(self, code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Código de recuperación de la clave")
        self.setMinimumWidth(560)
        intro = QLabel(
            "<b>Anote este código en un papel y guárdelo en un lugar seguro</b> (no lo pegue en la computadora).<br>"
            "Si algún día olvida su clave, en la pantalla de entrada pulse «¿Olvidó la clave de la dueña?» y escríbalo."
            "<br>No se volverá a mostrar."
        )
        intro.setWordWrap(True)
        code_label = QLabel(code)
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code_label.setStyleSheet(
            "font-family: Consolas, 'Courier New'; font-size: 28pt; font-weight: bold; letter-spacing: 3px;"
            " background: #fff8e1; border: 2px dashed #b28704; padding: 14px;"
        )
        self.done_check = QCheckBox("Ya lo anoté en papel")
        self.ok = QPushButton("Continuar")
        self.ok.setEnabled(False)
        self.ok.setAutoDefault(False)
        self.done_check.toggled.connect(self.ok.setEnabled)
        self.ok.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(code_label)
        row = QHBoxLayout()
        row.addWidget(self.done_check, 1)
        row.addWidget(self.ok)
        layout.addLayout(row)

    def reject(self) -> None:  # Esc no lo cierra sin confirmar que se anotó
        if self.done_check.isChecked():
            super().reject()


class RecoverPasswordDialog(QDialog):
    """Desde la pantalla de entrada: código de recuperación + clave nueva."""

    def __init__(self, conn: sqlite3.Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self.recovered_username: str | None = None
        self.setWindowTitle("Recuperar la clave de la dueña")
        self.setMinimumWidth(480)
        intro = QLabel(
            "Escriba el código de recuperación que anotó en papel (por ejemplo K7QM-3XR9-PW2H) y su clave nueva."
        )
        intro.setWordWrap(True)
        self.code = QLineEdit()
        self.code.setPlaceholderText("XXXX-XXXX-XXXX")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.EchoMode.Password)
        self.error = QLabel()
        self.error.setStyleSheet("color: #b00020;")
        self.error.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Código:", self.code)
        form.addRow("Clave nueva (mínimo 6):", self.password)
        form.addRow("Repita la clave:", self.password2)
        save = QPushButton("Cambiar la clave")
        cancel = QPushButton("Cancelar")
        for b in (save, cancel):
            b.setAutoDefault(False)
        save.clicked.connect(self._save)
        cancel.clicked.connect(super().reject)
        self.password2.returnPressed.connect(self._save)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(QLabel("¿Perdió también el código? Comuníquese con Borealis Software Solutions."))
        layout.addLayout(buttons)
        if not recovery_service.has_code(conn):
            self.error.setText("Este sistema todavía no tiene código de recuperación. Comuníquese con Borealis.")
            save.setEnabled(False)

    def _save(self) -> None:
        if self.password.text() != self.password2.text():
            self.error.setText("Las dos claves no coinciden.")
            return
        try:
            owner, new_code = recovery_service.reset_owner_password(self._conn, self.code.text(), self.password.text())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.recovered_username = owner.username
        QMessageBox.information(
            self,
            "Clave cambiada",
            f"Listo. Entre con el usuario «{owner.username}» y su clave nueva.\n"
            "El código que usó ya no sirve: a continuación verá uno nuevo para anotar.",
        )
        RecoveryCodeDialog(new_code, self).exec()
        self.accept()
