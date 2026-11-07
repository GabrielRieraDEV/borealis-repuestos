"""Pantalla de productos: búsqueda en vivo (RF-12) y acceso a la ficha."""

from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.products import UNIT_SHORT, Unit
from repuestos.domain.users import User
from repuestos.services import product_service
from repuestos.services.product_service import ProductView
from repuestos.ui.common import format_qty, run_action
from repuestos.ui.formatting import format_usd, format_ves
from repuestos.ui.product_dialog import ProductDialog

LOW_STOCK_BG = QColor("#ffe0e0")
LOW_STOCK_FG = QColor("#7f0000")
INACTIVE_FG = QColor("#9e9e9e")


class ProductTableModel(QAbstractTableModel):
    def __init__(self, show_cost: bool) -> None:
        super().__init__()
        self.rows: list[ProductView] = []
        self.columns = [
            "Código",
            "Nombre",
            "Marca",
            "Modelos",
            "Categoría",
            "Estante",
            "Existencia",
            "Precio Bs",
            "Precio USD",
        ]
        if show_cost:
            self.columns.append("Costo USD")

    def set_rows(self, rows: list[ProductView]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section]
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        v = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            unit = UNIT_SHORT[Unit(v.unit)]
            values = [
                v.code,
                v.name + ("" if v.active else "  (inactivo)"),
                v.brand,
                v.compatible_models,
                v.category_name,
                v.location,
                f"{format_qty(v.stock, v.allows_fraction)} {unit}" + ("  ▼ pedir" if v.is_low else ""),
                format_ves(v.price_ves) if v.price_ves is not None else "sin tasa",
                format_usd(v.price_usd),
            ]
            if len(self.columns) > len(values):
                values.append(format_usd(v.cost_usd) if v.cost_usd is not None else "")
            return values[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col >= 6:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and v.is_low:
            return QBrush(LOW_STOCK_BG)
        if role == Qt.ItemDataRole.ForegroundRole:
            if not v.active:
                return QBrush(INACTIVE_FG)
            if v.is_low:
                return QBrush(LOW_STOCK_FG)
        if role == Qt.ItemDataRole.ToolTipRole and v.is_low:
            return "Existencia en el mínimo o por debajo: para pedir"
        return None


class ProductsWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Productos")
        self.resize(1250, 680)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre, marca, modelo, categoría, código o código de barras (F2)")
        self.search.setClearButtonEnabled(True)
        self.show_inactive = QCheckBox("Mostrar inactivos")
        self.show_inactive.setVisible(user.is_owner)
        self.count_label = QLabel()

        self.model = ProductTableModel(show_cost=user.is_owner)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _: self._open_selected())

        self.new_button = QPushButton("Nuevo producto (Ctrl+N)")
        self.open_button = QPushButton("Abrir ficha (Enter)" if not user.is_owner else "Editar (Enter)")
        self.toggle_button = QPushButton("Desactivar / activar")
        for b in (self.new_button, self.toggle_button):
            b.setVisible(user.is_owner)
        self.new_button.clicked.connect(self._new)
        self.open_button.clicked.connect(self._open_selected)
        self.toggle_button.clicked.connect(self._toggle_active)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.show_inactive)
        bottom = QHBoxLayout()
        bottom.addWidget(self.count_label, 1)
        bottom.addWidget(self.new_button)
        bottom.addWidget(self.open_button)
        bottom.addWidget(self.toggle_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self.search.returnPressed.connect(self._search_enter)
        self.show_inactive.toggled.connect(lambda _: self.refresh())

        QShortcut(QKeySequence("F2"), self, activated=self._focus_search)
        if user.is_owner:
            QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new)
        down = QShortcut(QKeySequence(Qt.Key.Key_Down), self.search, activated=self._focus_table)
        down.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.table.installEventFilter(self)

        self.refresh()
        self.search.setFocus()

    # ------------------------------------------------------------------ búsqueda

    def refresh(self, select_id: int | None = None) -> None:
        rows = product_service.search(
            self._conn, self._user, self.search.text(), include_inactive=self.show_inactive.isChecked()
        )
        self.model.set_rows(rows)
        self.table.resizeColumnsToContents()
        n = len(rows)
        more = (
            " (se muestran los primeros; escriba más palabras para afinar)" if n >= product_service.SEARCH_LIMIT else ""
        )
        self.count_label.setText(f"{n} producto{'s' if n != 1 else ''}{more}")
        target = 0
        if select_id is not None:
            target = next((i for i, r in enumerate(rows) if r.id == select_id), 0)
        if rows:
            self.table.selectRow(target)

    def _search_enter(self) -> None:
        # Enter en la búsqueda: si el lector escribió un código exacto, abre ese producto
        self._debounce.stop()
        self.refresh()
        if self.model.rows:
            self._open_selected()

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _focus_table(self) -> None:
        if self.model.rows:
            self.table.setFocus()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.table and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._open_selected()
                return True
            if event.text().isprintable() and event.text().strip():
                self.search.setFocus()
                self.search.setText(self.search.text() + event.text())
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ acciones

    def _selected(self) -> ProductView | None:
        index = self.table.currentIndex()
        return self.model.rows[index.row()] if index.isValid() else None

    def _new(self) -> None:
        dialog = ProductDialog(self._conn, self._user, parent=self)
        last: list[int] = []
        dialog.saved.connect(last.append)
        dialog.exec()
        if last:
            self.refresh(select_id=last[-1])

    def _open_selected(self) -> None:
        v = self._selected()
        if v is None:
            return
        dialog = ProductDialog(self._conn, self._user, v.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh(select_id=v.id)

    def _toggle_active(self) -> None:
        v = self._selected()
        if v is None:
            return
        run_action(self, lambda: product_service.set_active(self._conn, self._user, v.id, not v.active))
        self.refresh(select_id=v.id)
