"""Ventana principal (PRD §6.2): accesos grandes, avisos y barra de estado."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QGridLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from repuestos.domain.users import ROLE_LABELS, User
from repuestos.services import product_service, rate_service, settings_service
from repuestos.services.rate_service import SOURCE_LABELS
from repuestos.ui.admin_dialogs import CategoriesDialog, SettingsDialog, UsersDialog
from repuestos.ui.formatting import format_date, format_rate
from repuestos.ui.inventory_window import InventoryWindow
from repuestos.ui.products_window import ProductsWindow
from repuestos.ui.purchases_window import PurchasesWindow
from repuestos.ui.rate import FETCH_INTERVAL_MS, BcvFetcher, RateDialog

NEXT_VERSION = "Disponible en una próxima actualización."
WARN_STYLE = "background: #fff3cd; color: #664d03; padding: 2px 6px;"
ERROR_STYLE = "background: #f8d7da; color: #842029; padding: 2px 6px;"


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, user: User) -> None:
        super().__init__()
        self._conn = conn
        self.user = user
        self.logout_requested = False
        business = settings_service.load(conn).business_name
        self.setWindowTitle(f"{business or 'Borealis Repuestos'} — Inventario, ventas y caja")
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
            self._big_button("Vender", enabled=False),
            self._big_button("Productos (F3)", self.open_products),
        ]
        if owner:
            buttons += [
                self._big_button("Compras", self.open_purchases),
                self._big_button("Inventario", lambda: self.open_inventory(0)),
            ]
        buttons += [
            self._big_button("Caja", enabled=False),
            self._big_button("Fiado", enabled=False),
            self._big_button("Reportes", enabled=False),
            self._big_button("Tasa BCV", self.open_rate),
        ]
        if owner:
            buttons += [
                self._big_button("Categorías", self.open_categories),
                self._big_button("Usuarios", self.open_users),
                self._big_button("Configuración", self.open_settings),
            ]
        for i, b in enumerate(buttons):
            grid.addWidget(b, i // 4, i % 4)
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
        welcome = QLabel(f"Hola, {self.user.full_name}")
        welcome.setStyleSheet("font-size: 18pt;")
        layout.addWidget(welcome)
        layout.addLayout(grid)
        layout.addWidget(self.alerts, 1)
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
        low = product_service.count_low_stock(self._conn)
        if low:
            text = f"• Para pedir: <b>{low}</b> producto{'s' if low != 1 else ''} en el mínimo o por debajo."
            if self.user.is_owner:
                text += ' <a href="pedir">Ver la lista</a>'
            alerts.append(text)
        self.alerts.setText("<br>".join(alerts))

    # ------------------------------------------------------------------ acciones

    def open_products(self) -> None:
        ProductsWindow(self._conn, self.user, self).exec()
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
        self.fetcher.shutdown()
        super().closeEvent(event)
