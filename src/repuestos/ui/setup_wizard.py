"""Asistente de primer arranque (RF-02)."""

from __future__ import annotations

import sqlite3

from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
    QWizard,
    QWizardPage,
)

from repuestos.domain.users import User
from repuestos.services import setup_service
from repuestos.ui.formatting import parse_decimal


def _page(title: str, subtitle: str) -> tuple[QWizardPage, QFormLayout]:
    page = QWizardPage()
    page.setTitle(title)
    page.setSubTitle(subtitle)
    form = QFormLayout(page)
    return page, form


class SetupWizard(QWizard):
    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self.user: User | None = None
        self.setWindowTitle("Configuración inicial")
        self.setMinimumWidth(560)
        self.setButtonText(QWizard.WizardButton.NextButton, "Siguiente >")
        self.setButtonText(QWizard.WizardButton.BackButton, "< Atrás")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Terminar")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Cancelar")

        # Página 1: la dueña
        page1, form1 = _page("Cuenta de la dueña", "Esta cuenta puede hacer todo en el sistema. Elija su contraseña.")
        self.owner_full_name = QLineEdit()
        self.owner_username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.EchoMode.Password)
        form1.addRow("Nombre completo:", self.owner_full_name)
        form1.addRow("Usuario:", self.owner_username)
        form1.addRow("Contraseña (mínimo 6):", self.password)
        form1.addRow("Repita la contraseña:", self.password2)
        self.addPage(page1)

        # Página 2: el negocio
        page2, form2 = _page("Datos del negocio", "Salen en la nota de entrega.")
        self.business_name = QLineEdit("PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P.")
        self.business_rif = QLineEdit("V-31463591-0")
        self.business_address = QLineEdit()
        self.business_phone = QLineEdit()
        form2.addRow("Razón social:", self.business_name)
        form2.addRow("RIF:", self.business_rif)
        form2.addRow("Domicilio fiscal:", self.business_address)
        form2.addRow("Teléfono:", self.business_phone)
        self.addPage(page2)

        # Página 3: precios, impresora y nube
        page3, form3 = _page(
            "Precios, impresora y respaldo",
            "El precio en bolívares se redondea hacia arriba al múltiplo indicado.",
        )
        self.rounding_multiple = QLineEdit("5,00")
        self.printer = QComboBox()
        self.printer.setEditable(True)
        self.printer.addItem("")
        self.printer.addItems(QPrinterInfo.availablePrinterNames())
        self.cloud_dir = QLineEdit()
        browse = QPushButton("Elegir carpeta…")
        browse.clicked.connect(self._choose_cloud_dir)
        cloud_row = QWidget()
        row = QHBoxLayout(cloud_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.cloud_dir)
        row.addWidget(browse)
        hint = QLabel("La impresora y la carpeta de la nube se pueden configurar después.")
        hint.setWordWrap(True)
        form3.addRow("Múltiplo de redondeo (Bs):", self.rounding_multiple)
        form3.addRow("Impresora de tickets:", self.printer)
        form3.addRow("Carpeta de respaldo en la nube:", cloud_row)
        form3.addRow(hint)
        self.addPage(page3)

    def _choose_cloud_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de respaldo en la nube")
        if folder:
            self.cloud_dir.setText(folder)

    def accept(self) -> None:
        if self.password.text() != self.password2.text():
            QMessageBox.warning(self, "Revise los datos", "Las dos contraseñas no coinciden.")
            return
        try:
            data = setup_service.SetupData(
                owner_username=self.owner_username.text(),
                owner_full_name=self.owner_full_name.text(),
                password=self.password.text(),
                business_name=self.business_name.text(),
                business_rif=self.business_rif.text(),
                business_address=self.business_address.text(),
                business_phone=self.business_phone.text(),
                rounding_multiple=parse_decimal(self.rounding_multiple.text()),
                printer_name=self.printer.currentText(),
                cloud_backup_dir=self.cloud_dir.text(),
            )
            self.user = setup_service.complete_setup(self._conn, data)
        except ValueError as exc:
            QMessageBox.warning(self, "Revise los datos", str(exc))
            return
        super().accept()
