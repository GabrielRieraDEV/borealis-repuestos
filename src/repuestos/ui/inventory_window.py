"""Inventario (dueña): "Para pedir" (RF-43), ajustes (RF-41) y conteo físico (RF-42)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.inventory import ADJUSTMENT_LABELS, AdjustmentKind
from repuestos.domain.products import UNIT_SHORT, Unit
from repuestos.domain.users import User
from repuestos.formatting import format_date, format_usd, parse_decimal
from repuestos.services import category_service, inventory_service
from repuestos.services.inventory_service import CountEntry, CountRow
from repuestos.services.product_service import ProductView
from repuestos.ui.common import decimal_field_text, format_qty, read_decimal, run_action
from repuestos.ui.product_picker import resolve_product

POSITIVE = QBrush(QColor("#1b5e20"))
NEGATIVE = QBrush(QColor("#b00020"))


def _item(text: str, right: bool = False, editable: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


def _signed(qty: Decimal, allows_fraction: bool) -> str:
    text = format_qty(abs(qty), allows_fraction)
    return ("+" if qty > 0 else "−" if qty < 0 else "") + text


# ------------------------------------------------------------------ para pedir


class ToOrderTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: User) -> None:
        super().__init__()
        self._conn = conn
        self._user = user
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Categoría", "Código", "Producto", "Marca", "Existencia", "Mínimo", "Último proveedor", "Último costo"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.summary = QLabel()
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(QLabel("La versión para imprimir (PDF) llega con los reportes."))
        bottom.addWidget(refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self) -> None:
        rows = inventory_service.to_order(self._conn, self._user)
        self.table.setRowCount(len(rows))
        previous = None
        for row, r in enumerate(rows):
            category = r.category_name or "(sin categoría)"
            unit = UNIT_SHORT[Unit(r.unit)]
            values = [
                (category if category != previous else "", False),
                (r.code, False),
                (r.name, False),
                (r.brand, False),
                (f"{format_qty(r.stock, r.allows_fraction)} {unit}", True),
                (f"{format_qty(r.min_stock, r.allows_fraction)} {unit}", True),
                (f"{r.last_supplier} ({format_date(r.last_purchase_date)})" if r.last_supplier else "—", False),
                (format_usd(r.last_cost, 4) if r.last_cost is not None else "—", True),
            ]
            previous = category
            for col, (text, right) in enumerate(values):
                item = _item(text, right)
                if col == 0 and text:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.summary.setText(f"{len(rows)} producto{'s' if len(rows) != 1 else ''} para pedir")


# ------------------------------------------------------------------ ajuste


class AdjustmentTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: User) -> None:
        super().__init__()
        self._conn = conn
        self._user = user
        self._product: ProductView | None = None
        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText("Escriba o escanee el producto y pulse Enter")
        self.product_label = QLabel("—")
        self.kind = QComboBox()
        for kind, label in ADJUSTMENT_LABELS.items():
            self.kind.addItem(label, kind.value)
        self.qty = QLineEdit()
        self.qty.setPlaceholderText("Cantidad (siempre positiva; el tipo dice si suma o resta)")
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Motivo (obligatorio)")
        self.result = QLabel()
        self.result.setWordWrap(True)
        save = QPushButton("Guardar ajuste")
        save.setAutoDefault(False)
        save.clicked.connect(self._save)
        form = QFormLayout()
        form.addRow("Producto:", self.product_input)
        form.addRow("", self.product_label)
        form.addRow("Tipo:", self.kind)
        form.addRow("Cantidad:", self.qty)
        form.addRow("Motivo:", self.reason)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.result)
        layout.addStretch(1)
        self.product_input.returnPressed.connect(self._choose)
        self.qty.returnPressed.connect(self.reason.setFocus)
        self.reason.returnPressed.connect(self._save)

    def _choose(self) -> None:
        p = resolve_product(self._conn, self._user, self.product_input.text(), self)
        if p is None:
            return
        self._product = p
        self.product_input.setText(p.name)
        self.product_label.setText(
            f"{p.code} — existencia actual {format_qty(p.stock, p.allows_fraction)} {UNIT_SHORT[Unit(p.unit)]}"
        )
        self.kind.setFocus()

    def _save(self) -> None:
        if self._product is None:
            self.product_input.setFocus()
            return
        p = self._product
        kind = AdjustmentKind(self.kind.currentData())
        result = run_action(
            self,
            lambda: inventory_service.adjust(
                self._conn, self._user, p.id, kind, read_decimal(self.qty, "Cantidad"), self.reason.text()
            ),
        )
        if result is None:
            return
        unit = UNIT_SHORT[Unit(p.unit)]
        self.result.setText(
            f"Ajuste guardado: {p.code} — {p.name} ({ADJUSTMENT_LABELS[kind].lower()}). Existencia: "
            f"{format_qty(result.stock_before, p.allows_fraction)} → "
            f"{format_qty(result.stock_after, p.allows_fraction)} {unit}."
        )
        self._product = None
        for w in (self.product_input, self.qty, self.reason):
            w.clear()
        self.product_label.setText("—")
        self.product_input.setFocus()


# ------------------------------------------------------------------ conteo físico


class CountTab(QWidget):
    COL_COUNTED = 5
    COL_DIFF = 6

    def __init__(self, conn: sqlite3.Connection, user: User) -> None:
        super().__init__()
        self._conn = conn
        self._user = user
        self.rows: list[CountRow] = []

        self.category = QComboBox()
        self.category.addItem("Todas las categorías", None)
        for c in category_service.list_categories(conn):
            self.category.addItem(c.name, c.id)
        self.location = QComboBox()
        self.location.addItem("Todos los estantes", "")
        for loc in inventory_service.locations(conn):
            self.location.addItem(loc, loc)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Búsqueda (opcional)")
        load = QPushButton("Cargar productos")
        load.setAutoDefault(False)
        load.clicked.connect(self.load)
        self.query.returnPressed.connect(self.load)
        filters = QHBoxLayout()
        filters.addWidget(self.category)
        filters.addWidget(self.location)
        filters.addWidget(self.query, 1)
        filters.addWidget(load)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Producto", "Categoría", "Estante", "En el sistema", "Contado", "Diferencia"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.AnyKeyPressed
            | QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.itemChanged.connect(self._item_changed)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Nota del conteo (opcional), p. ej. «estante A»")
        self.summary = QLabel("Elija categoría, estante o búsqueda y pulse «Cargar productos».")
        save = QPushButton("Guardar conteo")
        save.setAutoDefault(False)
        save.clicked.connect(self._save)
        bottom = QHBoxLayout()
        bottom.addWidget(self.note, 1)
        bottom.addWidget(save)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(QLabel("Escriba lo contado en la columna «Contado». Deje en blanco lo que no contó."))
        layout.addWidget(self.table, 1)
        layout.addWidget(self.summary)
        layout.addLayout(bottom)

    def load(self) -> None:
        if self._pending() and (
            QMessageBox.question(self, "Conteo", "Hay cantidades escritas sin guardar. ¿Descartarlas?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.rows = inventory_service.products_for_count(
            self._conn, self._user, self.category.currentData(), self.location.currentData(), self.query.text()
        )
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for row, r in enumerate(self.rows):
            unit = UNIT_SHORT[Unit(r.unit)]
            values = [
                _item(r.code),
                _item(r.name),
                _item(r.category_name),
                _item(r.location),
                _item(f"{format_qty(r.stock, r.allows_fraction)} {unit}", right=True),
                _item("", right=True, editable=True),
                _item("", right=True),
            ]
            for col, item in enumerate(values):
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.summary.setText(f"{len(self.rows)} productos cargados.")
        if self.rows:
            self.table.setCurrentCell(0, self.COL_COUNTED)
            self.table.setFocus()

    def _counted(self, row: int) -> Decimal | None:
        item = self.table.item(row, self.COL_COUNTED)
        text = item.text().strip() if item else ""
        return parse_decimal(text) if text else None

    def _pending(self) -> list[CountEntry]:
        entries = []
        for row, r in enumerate(self.rows):
            try:
                counted = self._counted(row)
            except ValueError:
                continue
            if counted is not None:
                entries.append(CountEntry(r.product_id, counted))
        return entries

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != self.COL_COUNTED:
            return
        row = item.row()
        r = self.rows[row]
        diff_item = self.table.item(row, self.COL_DIFF)
        self.table.blockSignals(True)
        try:
            counted = self._counted(row)
            if counted is None:
                diff_item.setText("")
            else:
                diff = counted - r.stock
                diff_item.setText(_signed(diff, r.allows_fraction) if diff else "cuadra")
                diff_item.setForeground(POSITIVE if diff > 0 else NEGATIVE if diff < 0 else QBrush())
        except ValueError:
            diff_item.setText("número inválido")
            diff_item.setForeground(NEGATIVE)
        finally:
            self.table.blockSignals(False)
        if row + 1 < len(self.rows):  # como una hoja de cálculo: Enter baja a la siguiente fila
            self.table.setCurrentCell(row + 1, self.COL_COUNTED)

    def _save(self) -> None:
        for row in range(len(self.rows)):
            try:
                self._counted(row)
            except ValueError:
                QMessageBox.warning(self, "Conteo", f"Fila {row + 1}: lo contado no es un número válido.")
                self.table.setCurrentCell(row, self.COL_COUNTED)
                return
        entries = self._pending()
        if not entries:
            QMessageBox.information(self, "Conteo", "No hay cantidades contadas para guardar.")
            return
        changes = sum(
            1 for e in entries if e.counted != next(r.stock for r in self.rows if r.product_id == e.product_id)
        )
        if (
            QMessageBox.question(
                self,
                "Guardar conteo",
                f"Se contaron {len(entries)} productos; {changes} tienen diferencia y se ajustarán.\n¿Guardar?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        results = run_action(
            self, lambda: inventory_service.register_count(self._conn, self._user, entries, self.note.text())
        )
        if results is None:
            return
        adjusted = [r for r in results if r.difference != 0]
        QMessageBox.information(
            self,
            "Conteo guardado",
            f"Conteo guardado: {len(results)} productos contados, {len(adjusted)} ajustados."
            + "".join(
                f"\n• {r.code} {r.name}: {decimal_field_text(r.system_stock, 3, strip=True)}"
                f" → {decimal_field_text(r.counted, 3, strip=True)}"
                for r in adjusted[:15]
            ),
        )
        self.note.clear()
        self.rows = []
        self.load()


# ------------------------------------------------------------------ ventana


class InventoryWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None, tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Inventario")
        self.resize(1150, 650)
        self.tabs = QTabWidget()
        self.to_order = ToOrderTab(conn, user)
        self.tabs.addTab(self.to_order, "Para pedir")
        self.tabs.addTab(AdjustmentTab(conn, user), "Ajuste (dañado, faltante, uso interno)")
        self.count = CountTab(conn, user)
        self.tabs.addTab(self.count, "Conteo físico")
        self.tabs.currentChanged.connect(lambda i: self.to_order.refresh() if i == 0 else None)
        self.tabs.setCurrentIndex(tab)
        close = QPushButton("Cerrar")
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def reject(self) -> None:
        if self.count._pending() and (
            QMessageBox.question(self, "Conteo sin guardar", "Hay un conteo sin guardar. ¿Salir igual?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        super().reject()

    def accept(self) -> None:
        self.reject() if self.count._pending() else super().accept()
