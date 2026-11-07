"""Diálogos de la dueña: categorías (RF-14), usuarios (RF-03) y configuración (RF-06)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.users import ROLE_LABELS, User
from repuestos.services import category_service, print_service, recovery_service, settings_service, user_service
from repuestos.ui.common import decimal_field_text, read_decimal, run_action
from repuestos.ui.recovery_ui import RecoveryCodeDialog

INACTIVE = QBrush(QColor("#9e9e9e"))


# ------------------------------------------------------------------ categorías


class CategoriesDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Categorías")
        self.resize(420, 480)
        self.list = QListWidget()
        new = QPushButton("Nueva")
        rename = QPushButton("Cambiar nombre")
        toggle = QPushButton("Desactivar / activar")
        close = QPushButton("Cerrar")
        new.clicked.connect(self._new)
        rename.clicked.connect(self._rename)
        toggle.clicked.connect(self._toggle)
        close.clicked.connect(self.accept)
        self.list.itemDoubleClicked.connect(lambda _: self._rename())
        buttons = QVBoxLayout()
        for b in (new, rename, toggle):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QHBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self, select_id: int | None = None) -> None:
        self.list.clear()
        for c in category_service.list_categories(self._conn, include_inactive=True):
            item = QListWidgetItem(c.name + ("" if c.active else "  (inactiva)"))
            item.setData(Qt.ItemDataRole.UserRole, (c.id, c.name, c.active))
            if not c.active:
                item.setForeground(INACTIVE)
            self.list.addItem(item)
            if c.id == select_id:
                self.list.setCurrentItem(item)

    def _current(self) -> tuple[int, str, bool] | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva categoría", "Nombre:")
        if ok:
            cid = run_action(self, lambda: category_service.create_category(self._conn, self._user, name))
            self.refresh(cid)

    def _rename(self) -> None:
        current = self._current()
        if current is None:
            return
        name, ok = QInputDialog.getText(self, "Cambiar nombre", "Nombre:", text=current[1])
        if ok:
            run_action(self, lambda: category_service.rename_category(self._conn, self._user, current[0], name))
            self.refresh(current[0])

    def _toggle(self) -> None:
        current = self._current()
        if current is None:
            return
        run_action(self, lambda: category_service.set_active(self._conn, self._user, current[0], not current[2]))
        self.refresh(current[0])


# ------------------------------------------------------------------ usuarios


class NewSellerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo vendedor")
        self.full_name = QLineEdit()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout(self)
        form.addRow("Nombre completo:", self.full_name)
        form.addRow("Usuario:", self.username)
        form.addRow("Contraseña (mínimo 6):", self.password)
        form.addRow("Repita la contraseña:", self.password2)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Crear")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


def _ask_new_password(parent: QWidget, who: str) -> str | None:
    p1, ok = QInputDialog.getText(
        parent, "Nueva contraseña", f"Nueva contraseña para {who}:", QLineEdit.EchoMode.Password
    )
    if not ok:
        return None
    p2, ok = QInputDialog.getText(parent, "Nueva contraseña", "Repítala:", QLineEdit.EchoMode.Password)
    if not ok:
        return None
    if p1 != p2:
        QMessageBox.warning(parent, "Contraseña", "Las dos contraseñas no coinciden.")
        return None
    return p1


class UsersDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Usuarios")
        self.resize(640, 400)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Usuario", "Nombre", "Rol", "Estado"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        new = QPushButton("Nuevo vendedor")
        reset = QPushButton("Restablecer contraseña")
        toggle = QPushButton("Desactivar / activar")
        close = QPushButton("Cerrar")
        recovery = QPushButton("Código de recuperación…")
        recovery.clicked.connect(self._recovery_code)
        new.clicked.connect(self._new)
        reset.clicked.connect(self._reset)
        toggle.clicked.connect(self._toggle)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        for b in (new, reset, toggle, recovery):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self.users: list[User] = []
        self.refresh()

    def refresh(self) -> None:
        self.users = user_service.list_users(self._conn, self._user)
        self.table.setRowCount(len(self.users))
        for row, u in enumerate(self.users):
            values = [u.username, u.full_name, ROLE_LABELS[u.role], "Activo" if u.active else "Inactivo"]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if not u.active:
                    item.setForeground(INACTIVE)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def _current(self) -> User | None:
        row = self.table.currentRow()
        return self.users[row] if 0 <= row < len(self.users) else None

    def _new(self) -> None:
        d = NewSellerDialog(self)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if d.password.text() != d.password2.text():
            QMessageBox.warning(self, "Contraseña", "Las dos contraseñas no coinciden.")
            return
        run_action(
            self,
            lambda: user_service.create_seller(
                self._conn, self._user, d.username.text(), d.full_name.text(), d.password.text()
            ),
        )
        self.refresh()

    def _reset(self) -> None:
        u = self._current()
        if u is None:
            return
        password = _ask_new_password(self, u.full_name)
        if password is not None and run_action(
            self, lambda: user_service.reset_password(self._conn, self._user, u.id, password) or True
        ):
            QMessageBox.information(self, "Contraseña", f"Contraseña de {u.full_name} cambiada.")

    def _toggle(self) -> None:
        u = self._current()
        if u is None:
            return
        run_action(self, lambda: user_service.set_active(self._conn, self._user, u.id, not u.active))
        self.refresh()

    def _recovery_code(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Código de recuperación",
                "Se creará un código nuevo para recuperar SU clave si la olvida. El código anterior dejará de servir."
                " ¿Continuar?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        code = run_action(self, lambda: recovery_service.generate_code(self._conn, self._user))
        if code is not None:
            RecoveryCodeDialog(code, self).exec()


# ------------------------------------------------------------------ configuración


class SettingsDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._settings = settings_service.load(conn)
        s = self._settings
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(620)

        self.business_name = QLineEdit(s.business_name)
        self.business_rif = QLineEdit(s.business_rif)
        self.business_address = QLineEdit(s.business_address)
        self.business_address.setPlaceholderText("Por defecto, el domicilio fiscal del RIF")
        self.business_phone = QLineEdit(s.business_phone)
        self.rounding = QLineEdit(decimal_field_text(s.rounding_multiple, 2))
        self.min_stock = QLineEdit(decimal_field_text(s.default_min_stock, 3, strip=True))
        self.credit_days = QSpinBox()
        self.credit_days.setRange(1, 365)
        self.credit_days.setValue(s.default_credit_days)
        self.usdt = QCheckBox("Aceptar Binance USDT como forma de pago")
        self.usdt.setChecked(s.payment_usdt_enabled)
        self.negative = QCheckBox("Permitir vender aunque la existencia quede negativa")
        self.negative.setChecked(s.allow_negative_stock)
        self.igtf = QLineEdit(decimal_field_text(s.igtf_percent, 2))
        self.igtf.setToolTip("Se guarda para el futuro; en esta versión no se aplica.")
        self.printer = QComboBox()
        self.printer.setEditable(True)
        self.printer.addItem("")
        self.printer.addItems(QPrinterInfo.availablePrinterNames())
        self.printer.setCurrentText(s.printer_name)
        test_print = QPushButton("Imprimir prueba")
        test_print.setAutoDefault(False)
        test_print.clicked.connect(self._test_print)
        printer_row = QWidget()
        prow = QHBoxLayout(printer_row)
        prow.setContentsMargins(0, 0, 0, 0)
        prow.addWidget(self.printer, 1)
        prow.addWidget(test_print)
        self.cloud_dir = QLineEdit(s.cloud_backup_dir)
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self._choose_cloud_dir)
        cloud_row = QWidget()
        row = QHBoxLayout(cloud_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.cloud_dir, 1)
        row.addWidget(browse)
        self.large_font = QCheckBox("Letra grande (se aplica al volver a abrir el programa)")
        self.large_font.setChecked(s.large_font)

        form = QFormLayout()
        form.addRow(QLabel("<b>Negocio</b>"))
        form.addRow("Razón social:", self.business_name)
        form.addRow("RIF:", self.business_rif)
        form.addRow("Domicilio fiscal:", self.business_address)
        form.addRow("Teléfono:", self.business_phone)
        form.addRow(QLabel("<b>Precios e inventario</b>"))
        form.addRow("Múltiplo de redondeo (Bs):", self.rounding)
        form.addRow("Mínimo por defecto:", self.min_stock)
        form.addRow("", self.negative)
        form.addRow(QLabel("<b>Cobro y fiado</b>"))
        form.addRow("Plazo de fiado (días):", self.credit_days)
        form.addRow("", self.usdt)
        form.addRow("IGTF %:", self.igtf)
        form.addRow(QLabel("<b>Equipo</b>"))
        form.addRow("Impresora de tickets:", printer_row)
        form.addRow("Carpeta de respaldo en la nube:", cloud_row)
        form.addRow("", self.large_font)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _test_print(self) -> None:
        try:
            print_service.print_test(self._conn, self.printer.currentText())
        except print_service.PrintError as exc:
            QMessageBox.warning(self, "Impresora", str(exc))
            return
        QMessageBox.information(
            self, "Impresora", "Se envió la página de prueba. Si salió completa, guarde la configuración."
        )

    def _choose_cloud_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de respaldo en la nube", self.cloud_dir.text())
        if folder:
            self.cloud_dir.setText(folder)

    def _save(self) -> None:
        def action() -> bool:
            new = replace(
                self._settings,
                business_name=self.business_name.text(),
                business_rif=self.business_rif.text(),
                business_address=self.business_address.text(),
                business_phone=self.business_phone.text(),
                rounding_multiple=read_decimal(self.rounding, "Múltiplo de redondeo"),
                default_min_stock=read_decimal(self.min_stock, "Mínimo por defecto"),
                default_credit_days=self.credit_days.value(),
                payment_usdt_enabled=self.usdt.isChecked(),
                allow_negative_stock=self.negative.isChecked(),
                igtf_percent=read_decimal(self.igtf, "IGTF"),
                printer_name=self.printer.currentText(),
                cloud_backup_dir=self.cloud_dir.text(),
                large_font=self.large_font.isChecked(),
            )
            settings_service.save(self._conn, self._user, new)
            return True

        if run_action(self, action):
            self.accept()
