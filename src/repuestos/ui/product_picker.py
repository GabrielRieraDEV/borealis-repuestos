"""Elegir un producto con el teclado: escaneo exacto directo, o búsqueda con lista (Enter elige, Esc cancela).

Se reutiliza en compras, ajustes y (Fase 3) en la venta.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractItemView, QDialog, QLabel, QLineEdit, QTableView, QVBoxLayout, QWidget

from repuestos.domain.users import User
from repuestos.services import product_service
from repuestos.services.product_service import ProductView
from repuestos.ui.products_window import ProductTableModel


class ProductPicker(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, query: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.selected: ProductView | None = None
        self.setWindowTitle("Buscar producto")
        self.resize(1100, 560)

        self.search = QLineEdit(query)
        self.search.setPlaceholderText("Escriba palabras del nombre, marca, modelo o código. Enter elige.")
        self.model = ProductTableModel(show_cost=user.is_owner)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _: self._choose())
        self.hint = QLabel("↑ ↓ para moverse · Enter para elegir · Esc para cancelar")

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.hint)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self.search.returnPressed.connect(self._choose)
        for key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            sc = QShortcut(QKeySequence(key), self.search, activated=lambda k=key: self._move(k))
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.table.activated.connect(lambda _: self._choose())
        self.refresh()
        self.search.setFocus()
        self.search.end(False)

    def refresh(self) -> None:
        self.model.set_rows(product_service.search(self._conn, self._user, self.search.text()))
        self.table.resizeColumnsToContents()
        if self.model.rows:
            self.table.selectRow(0)

    def _move(self, key: Qt.Key) -> None:
        if not self.model.rows:
            return
        row = self.table.currentIndex().row()
        row = min(row + 1, len(self.model.rows) - 1) if key == Qt.Key.Key_Down else max(row - 1, 0)
        self.table.selectRow(row)

    def _choose(self) -> None:
        self._debounce.stop()
        if self.search.text() and not self.model.rows:
            self.refresh()
        index = self.table.currentIndex()
        if not index.isValid():
            return
        self.selected = self.model.rows[index.row()]
        self.accept()


def resolve_product(
    conn: sqlite3.Connection, user: User, text: str, parent: QWidget | None = None
) -> ProductView | None:
    """Lo escrito o escaneado: código exacto → directo; una sola coincidencia → directo; si no, la lista."""
    text = text.strip()
    if text:
        hit = product_service.find_by_scan(conn, user, text)
        if hit is not None:
            return hit
        results = product_service.search(conn, user, text, limit=2)
        if len(results) == 1:
            return results[0]
    picker = ProductPicker(conn, user, text, parent)
    return picker.selected if picker.exec() == QDialog.DialogCode.Accepted else None
