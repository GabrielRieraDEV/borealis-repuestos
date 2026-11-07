"""Ventana principal (PRD §6.2): accesos grandes, avisos y barra de estado."""

from __future__ import annotations

import os
import sqlite3
from importlib import resources

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QGridLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from repuestos import __version__
from repuestos.config import BRAND, get_paths, is_test_mode
from repuestos.domain.money import ZERO
from repuestos.domain.users import ROLE_LABELS, User
from repuestos.formatting import format_date, format_rate, format_usd
from repuestos.services import (
    backup_service,
    cash_service,
    credit_service,
    product_service,
    rate_service,
    recovery_service,
    settings_service,
)
from repuestos.services.rate_service import SOURCE_LABELS
from repuestos.ui.admin_dialogs import CategoriesDialog, SettingsDialog, UsersDialog
from repuestos.ui.backup_ui import BackupDialog, BackupManager
from repuestos.ui.brand import brand_label, test_mode_banner
from repuestos.ui.cash_window import CashWindow
from repuestos.ui.credit_window import CreditWindow
from repuestos.ui.inventory_window import InventoryWindow
from repuestos.ui.products_window import ProductsWindow
from repuestos.ui.purchases_window import PurchasesWindow
from repuestos.ui.rate import FETCH_INTERVAL_MS, BcvFetcher, RateDialog
from repuestos.ui.reports_window import AuditWindow, ReportsWindow
from repuestos.ui.sale_window import SaleWindow
from repuestos.ui.sales_list import SalesListWindow

NEXT_VERSION = "Disponible en una próxima actualización."
WARN_STYLE = "background: #fff3cd; color: #664d03; padding: 2px 6px;"
ERROR_STYLE = "background: #f8d7da; color: #842029; padding: 2px 6px;"


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, user: User) -> None:
        super().__init__()
        self._conn = conn
        self.user = user
        self.logout_requested = False
        self.restore_path = None  # respaldo a restaurar: app.py cierra la base, restaura y reinicia (RF-91)
        self.backup = BackupManager(self)
        self.backup.finished.connect(self._backup_finished)
        self._backup_error: str | None = None
        business = settings_service.load(conn).business_name
        prefix = "MODO DE PRUEBA — " if is_test_mode() else ""
        self.setWindowTitle(
            f"{prefix}{business or 'Borealis Repuestos'} — Inventario, ventas y caja · Borealis Repuestos"
        )
        self.resize(1200, 720)

        self._build_menu()
        self._build_center()
        self._build_status_bar()

        self.fetcher = BcvFetcher(conn, self)
        self.fetcher.updated.connect(self.refresh_status)
        self.fetcher.finished.connect(lambda ok, msg: self.refresh_status())
        self._fetch_timer = QTimer(self)
        self._fetch_timer.setInterval(FETCH_INTERVAL_MS)
        self._fetch_timer.timeout.connect(self.fetcher.start)
        self._fetch_timer.start()
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(60_000)
        self._status_timer.timeout.connect(self.refresh_status)
        self._status_timer.start()

        self.refresh_status()
        QTimer.singleShot(0, self.fetcher.start)  # al arrancar (RF-20), sin bloquear
        self._startup_backup = QTimer(self)  # al arrancar si el último tiene más de 12 h (RF-90)
        self._startup_backup.setSingleShot(True)
        self._startup_backup.setInterval(1500)
        self._startup_backup.timeout.connect(lambda: self.backup.start())
        if backup_service.needs_backup(conn):
            self._startup_backup.start()

    # ------------------------------------------------------------------ construcción

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&Sesión")
        logout = QAction("Cerrar sesión", self)
        logout.triggered.connect(self._logout)
        leave = QAction("Salir", self)
        leave.setShortcut(QKeySequence("Ctrl+Q"))
        leave.triggered.connect(self.close)
        menu.addAction(logout)
        menu.addAction(leave)
        help_menu = self.menuBar().addMenu("A&yuda")
        guide = QAction("Guía rápida", self)
        guide.setShortcut(QKeySequence("F1"))
        guide.triggered.connect(self.open_guide)
        about = QAction("Acerca del programa", self)
        about.triggered.connect(self.open_about)
        help_menu.addAction(guide)
        help_menu.addAction(about)

    def _big_button(self, text: str, slot=None, enabled: bool = True) -> QPushButton:
        b = QPushButton(text)
        b.setMinimumSize(200, 90)
        b.setStyleSheet("font-size: 15pt;")
        if slot is not None and enabled:
            b.clicked.connect(slot)
        else:
            b.setEnabled(False)
            b.setToolTip(NEXT_VERSION)
        return b

    def _build_center(self) -> None:
        owner = self.user.is_owner
        grid = QGridLayout()
        buttons = [
            self._big_button("Vender (F5)", self.open_sale),
            self._big_button("Productos (F3)", self.open_products),
            self._big_button("Caja", self.open_cash),
            self._big_button("Ventas del día", self.open_sales),
        ]
        if owner:
            buttons += [
                self._big_button("Compras", self.open_purchases),
                self._big_button("Inventario", lambda: self.open_inventory(0)),
            ]
        buttons += [
            self._big_button("Fiado", self.open_credit),
            self._big_button("Reportes", self.open_reports),
            self._big_button("Tasa BCV", self.open_rate),
        ]
        if owner:
            buttons += [
                self._big_button("Categorías", self.open_categories),
                self._big_button("Usuarios", self.open_users),
                self._big_button("Configuración", self.open_settings),
                self._big_button("Respaldo", self.open_backup),
                self._big_button("Bitácora", self.open_audit),
            ]
        for i, b in enumerate(buttons):
            grid.addWidget(b, i // 4, i % 4)
        sale_action = QAction(self)
        sale_action.setShortcut(QKeySequence("F5"))
        sale_action.triggered.connect(self.open_sale)
        self.addAction(sale_action)
        products_action = QAction(self)
        products_action.setShortcut(QKeySequence("F3"))
        products_action.triggered.connect(self.open_products)
        self.addAction(products_action)

        self.alerts = QLabel()
        self.alerts.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.alerts.setStyleSheet("font-size: 13pt;")
        self.alerts.setWordWrap(True)
        self.alerts.linkActivated.connect(self._alert_link)

        center = QWidget()
        layout = QVBoxLayout(center)
        banner = test_mode_banner()
        if banner is not None:
            layout.addWidget(banner)
        welcome = QLabel(f"Hola, {self.user.full_name}")
        welcome.setStyleSheet("font-size: 18pt;")
        layout.addWidget(welcome)
        layout.addLayout(grid)
        layout.addWidget(self.alerts, 1)
        layout.addWidget(brand_label(), 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(center)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self.user_label = QLabel(f"Usuario: {self.user.full_name} ({ROLE_LABELS[self.user.role]})")
        self.rate_label = QLabel()
        self.cash_label = QLabel("Caja: cerrada")
        self.backup_label = QLabel("Respaldo: nunca")
        for label in (self.user_label, self.rate_label, self.cash_label, self.backup_label):
            label.setContentsMargins(8, 0, 8, 0)
            bar.addPermanentWidget(label)

    # ------------------------------------------------------------------ estado

    def refresh_status(self) -> None:
        r = rate_service.current_rate(self._conn)
        alerts: list[str] = []
        if r is None:
            self.rate_label.setText("Tasa: sin tasa")
            self.rate_label.setStyleSheet(ERROR_STYLE)
            alerts.append("• No hay tasa del día: cárguela en <b>Tasa BCV</b> para poder vender.")
        else:
            self.rate_label.setText(
                f"Tasa: {format_rate(r.rate)} ({format_date(r.valid_date)}, {SOURCE_LABELS[r.source]})"
            )
            self.rate_label.setStyleSheet(WARN_STYLE if r.stale else "")
            if r.stale:
                alerts.append("• La tasa tiene más de 3 días. Revise <b>Tasa BCV</b>.")
        session = cash_service.current_session(self._conn)
        if session is None:
            self.cash_label.setText("Caja: cerrada")
            alerts.append("• La caja está cerrada: ábrala en <b>Caja</b> para vender.")
        else:
            self.cash_label.setText(
                f"Caja: abierta desde {session.opened_at[11:16]} ({format_date(session.opened_at)})"
            )
        low = product_service.count_low_stock(self._conn)
        if low:
            text = f"• Para pedir: <b>{low}</b> producto{'s' if low != 1 else ''} en el mínimo o por debajo."
            if self.user.is_owner:
                text += ' <a href="pedir">Ver la lista</a>'
            alerts.append(text)
        overdue = [d for d in credit_service.debtors(self._conn) if d.overdue_usd > 0]
        if overdue:
            total = sum((d.overdue_usd for d in overdue), ZERO)
            n = len(overdue)
            alerts.append(
                f"• Fiado vencido: <b>{n}</b> cliente{'s' if n != 1 else ''} por <b>{format_usd(total)}</b>."
                ' <a href="fiado">Ver deudores</a>'
            )
        if self.user.is_owner and not recovery_service.has_code(self._conn):
            alerts.append("• Falta el código de recuperación de su clave: genérelo en <b>Usuarios</b> y anótelo.")
        self._refresh_backup_label(alerts)
        self.alerts.setText("<br>".join(alerts))

    def _refresh_backup_label(self, alerts: list[str]) -> None:
        st = backup_service.status(self._conn)
        if self._backup_error:
            self.backup_label.setText("Respaldo: falló")
            self.backup_label.setToolTip(self._backup_error)
            self.backup_label.setStyleSheet(ERROR_STYLE)
            alerts.append("• El último respaldo falló. Avise a Borealis.")
            return
        self.backup_label.setToolTip("")
        if st.last_local is None:
            self.backup_label.setText("Respaldo: nunca")
            self.backup_label.setStyleSheet(WARN_STYLE)
            return
        if not st.cloud_configured:
            self.backup_label.setText(f"Respaldo: local {st.last_local:%d/%m %H:%M} (sin nube)")
            self.backup_label.setStyleSheet(WARN_STYLE)
            if self.user.is_owner:
                alerts.append("• Falta configurar la carpeta de la nube para el respaldo (Configuración).")
            return
        when = f"{st.last_cloud:%d/%m %H:%M}" if st.last_cloud else "nunca"
        self.backup_label.setText(f"Respaldo en la nube: {when}")
        self.backup_label.setStyleSheet(WARN_STYLE if st.cloud_stale else "")
        if st.cloud_stale:
            alerts.append("• El respaldo en la nube tiene más de 48 horas. Revise que Google Drive esté abierto.")

    def _backup_finished(self, ok: bool, message: str) -> None:
        self._backup_error = None if ok or "nube" in message else message
        self.refresh_status()

    # ------------------------------------------------------------------ acciones

    def open_products(self) -> None:
        ProductsWindow(self._conn, self.user, self).exec()
        self.refresh_status()

    def open_sale(self) -> None:
        if rate_service.current_rate(self._conn) is None:
            QMessageBox.warning(self, "Sin tasa", "No hay tasa del día. Cárguela en Tasa BCV.")
            return
        if cash_service.current_session(self._conn) is None:
            QMessageBox.warning(self, "Caja cerrada", cash_service.NO_OPEN_SESSION)
            return
        SaleWindow(self._conn, self.user, self).exec()
        self.refresh_status()

    def open_cash(self) -> None:
        # al cerrar caja: respaldo + PDF en la nube (RF-62, RF-90, RF-92)
        CashWindow(self._conn, self.user, self, on_closed=lambda: self.backup.start(with_pdfs=True)).exec()
        self.refresh_status()

    def open_reports(self) -> None:
        ReportsWindow(self._conn, self.user, self).exec()

    def open_audit(self) -> None:
        AuditWindow(self._conn, self.user, self).exec()

    def open_backup(self) -> None:
        dialog = BackupDialog(self._conn, self.user, self.backup, self)
        dialog.exec()
        self.refresh_status()
        if dialog.restore_path is not None:
            self.restore_path = dialog.restore_path
            self.close()

    def open_credit(self) -> None:
        CreditWindow(self._conn, self.user, self).exec()
        self.refresh_status()

    def open_sales(self) -> None:
        SalesListWindow(self._conn, self.user, self).exec()
        self.refresh_status()

    def open_purchases(self) -> None:
        PurchasesWindow(self._conn, self.user, self).exec()
        self.refresh_status()

    def open_inventory(self, tab: int = 0) -> None:
        InventoryWindow(self._conn, self.user, self, tab=tab).exec()
        self.refresh_status()

    def _alert_link(self, link: str) -> None:
        if link == "pedir" and self.user.is_owner:
            self.open_inventory(0)
        elif link == "fiado":
            self.open_credit()

    def open_rate(self) -> None:
        RateDialog(self._conn, self.user, self.fetcher, self).exec()
        self.refresh_status()

    def open_categories(self) -> None:
        CategoriesDialog(self._conn, self.user, self).exec()

    def open_users(self) -> None:
        UsersDialog(self._conn, self.user, self).exec()

    def open_settings(self) -> None:
        SettingsDialog(self._conn, self.user, self).exec()
        self.refresh_status()

    def open_guide(self) -> None:
        path = resources.files("repuestos.ui") / "guia-rapida.pdf"
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            QMessageBox.information(self, "Guía rápida", f"La guía está en:\n{path}")

    def open_about(self) -> None:
        QMessageBox.about(
            self,
            "Acerca del programa",
            f"<b>Borealis Repuestos</b> versión {__version__}<br>"
            "Inventario, ventas y caja para Romero Alfa 1.<br><br>"
            f"Hecho por <b>{BRAND}</b>. Sin licencia que caduque: el programa es suyo.<br>"
            f"Datos en {get_paths().base}",
        )

    def show_stock_mismatch(self, count: int) -> None:
        QMessageBox.warning(
            self,
            "Revisión de existencias",
            f"{count} producto(s) tienen una existencia que no cuadra con sus movimientos.\n"
            "Quedó anotado en la bitácora. Avise a Borealis para revisarlo.",
        )

    def _logout(self) -> None:
        self.logout_requested = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._fetch_timer.stop()
        self._status_timer.stop()
        self._startup_backup.stop()
        self.fetcher.shutdown()
        self.backup.wait()
        super().closeEvent(event)
