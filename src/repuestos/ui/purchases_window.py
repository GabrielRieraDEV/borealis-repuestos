"""Compras (RF-30 a RF-32): lista con filtros, registro con teclado, ayuda por empaque, detalle y anulación."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.money import ZERO
from repuestos.domain.pricing import pack_purchase, purchase_line_total
from repuestos.domain.products import UNIT_SHORT, Unit
from repuestos.domain.users import User
from repuestos.services import purchase_service
from repuestos.services.product_service import ProductView
from repuestos.services.purchase_service import PurchaseLineInput
from repuestos.ui.common import decimal_field_text, format_qty, read_decimal, run_action
from repuestos.ui.formatting import format_date, format_usd
from repuestos.ui.product_dialog import money_text
from repuestos.ui.product_picker import resolve_product


def _no_default(*buttons: QPushButton) -> None:
    """Enter nunca dispara un botón: cada campo decide qué hace con Enter."""
    for b in buttons:
        b.setAutoDefault(False)
        b.setDefault(False)


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pydate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def _item(text: str, right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


# ------------------------------------------------------------------ ayuda por empaque


class PackDialog(QDialog):
    """ "N empaques × M unidades a X USD el empaque" → cantidad y costo unitario (RN-08)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compra por empaque")
        self.result_qty: Decimal | None = None
        self.result_cost: Decimal | None = None
        self.packs = QLineEdit()
        self.units = QLineEdit()
        self.pack_cost = QLineEdit()
        self.preview = QLabel()
        for w in (self.packs, self.units, self.pack_cost):
            w.textChanged.connect(self._update)
        form = QFormLayout(self)
        form.addRow("Empaques (cajas, docenas…):", self.packs)
        form.addRow("Unidades por empaque:", self.units)
        form.addRow("Costo del empaque USD:", self.pack_cost)
        form.addRow(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Usar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _calc(self):
        return pack_purchase(
            read_decimal(self.packs, "Empaques"),
            read_decimal(self.units, "Unidades por empaque"),
            read_decimal(self.pack_cost, "Costo del empaque"),
        )

    def _update(self) -> None:
        try:
            p = self._calc()
            self.preview.setText(
                f"= {decimal_field_text(p.qty, 3, strip=True)} unidades a {format_usd(p.unit_cost, 4)}"
            )
        except (ValueError, ArithmeticError):
            self.preview.setText("")

    def _accept(self) -> None:
        p = run_action(self, self._calc, "Revise los datos")
        if p is not None:
            self.result_qty, self.result_cost = p.qty, p.unit_cost
            self.accept()


# ------------------------------------------------------------------ registrar compra


@dataclass
class _Line:
    product: ProductView
    qty: Decimal
    unit_cost: Decimal

    @property
    def total(self) -> Decimal:
        return purchase_line_total(self.qty, self.unit_cost)


class PurchaseDialog(QDialog):
    """Teclado: escriba o escanee el producto + Enter → cantidad + Enter → costo + Enter agrega el renglón.
    F2 busca · F4 por empaque · Supr quita el renglón · Ctrl+S guarda · Esc cancela."""

    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.lines: list[_Line] = []
        self._current: ProductView | None = None
        self.saved_id: int | None = None
        self.setWindowTitle("Registrar compra")
        self.resize(1050, 640)

        # encabezado
        self.supplier = QComboBox()
        self._load_suppliers()
        new_supplier = QPushButton("Nuevo proveedor…")
        new_supplier.clicked.connect(self._new_supplier)
        supplier_row = QHBoxLayout()
        supplier_row.addWidget(self.supplier, 1)
        supplier_row.addWidget(new_supplier)
        self.invoice = QLineEdit()
        self.invoice.setPlaceholderText("Número de factura del proveedor (opcional)")
        self.date = QDateEdit(_qdate(date.today()))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setMaximumDate(_qdate(date.today()))
        header = QFormLayout()
        header.addRow("Proveedor:", supplier_row)
        header.addRow("Factura:", self.invoice)
        header.addRow("Fecha:", self.date)

        # captura de renglón
        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText("Producto: escriba o escanee y pulse Enter (F2 buscar)")
        self.product_label = QLabel("—")
        self.qty = QLineEdit()
        self.qty.setPlaceholderText("Cantidad")
        self.qty.setMaximumWidth(110)
        self.cost = QLineEdit()
        self.cost.setPlaceholderText("Costo unit. USD")
        self.cost.setMaximumWidth(140)
        pack = QPushButton("Por empaque (F4)")
        add = QPushButton("Agregar (Enter)")
        pack.clicked.connect(self._pack)
        add.clicked.connect(self._add_line)
        entry = QHBoxLayout()
        entry.addWidget(self.product_input, 2)
        entry.addWidget(self.qty)
        entry.addWidget(self.cost)
        entry.addWidget(pack)
        entry.addWidget(add)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Código", "Producto", "Cantidad", "Costo unit. USD", "Total USD"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Notas (opcional)")
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 15pt; font-weight: bold;")
        save = QPushButton("Guardar compra (Ctrl+S)")
        cancel = QPushButton("Cancelar (Esc)")
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        _no_default(new_supplier, pack, add, save, cancel)
        bottom = QHBoxLayout()
        bottom.addWidget(self.notes, 1)
        bottom.addWidget(self.total_label)
        bottom.addWidget(save)
        bottom.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(entry)
        layout.addWidget(self.product_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

        self.product_input.returnPressed.connect(lambda: self._choose_product(self.product_input.text()))
        self.qty.returnPressed.connect(self._qty_enter)
        self.cost.returnPressed.connect(self._add_line)
        QShortcut(QKeySequence("F2"), self, activated=lambda: self._choose_product(self.product_input.text(), True))
        QShortcut(QKeySequence("F4"), self, activated=self._pack)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save)
        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table, activated=self._remove_line)
        delete.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._refresh_table()
        (self.supplier if self.supplier.currentData() is None else self.product_input).setFocus()

    # ------------------------------------------------------------------ proveedor

    def _load_suppliers(self, select_id: int | None = None) -> None:
        self.supplier.clear()
        self.supplier.addItem("(elija un proveedor)", None)
        for s in purchase_service.list_suppliers(self._conn):
            self.supplier.addItem(s.name, s.id)
        if select_id is not None:
            self.supplier.setCurrentIndex(self.supplier.findData(select_id))

    def _new_supplier(self) -> None:
        name, ok = QInputDialog.getText(self, "Nuevo proveedor", "Nombre del proveedor:")
        if ok and name.strip():
            s = run_action(self, lambda: purchase_service.create_supplier(self._conn, self._user, name))
            if s is not None:
                self._load_suppliers(s.id)
                self.product_input.setFocus()

    # ------------------------------------------------------------------ renglones

    def _choose_product(self, text: str, force_list: bool = False) -> None:
        product = resolve_product(self._conn, self._user, "" if force_list and not text else text, self)
        if product is None:
            return
        if not product.active:
            QMessageBox.warning(self, "Producto inactivo", "Ese producto está inactivo. Actívelo en Productos.")
            return
        self._current = product
        unit = UNIT_SHORT[Unit(product.unit)]
        self.product_label.setText(
            f"{product.code} — {product.name}   ·   existencia {format_qty(product.stock, product.allows_fraction)}"
            f" {unit}   ·   costo promedio {format_usd(product.cost_usd or ZERO, 4)}"
        )
        self.product_input.setText(product.name)
        if product.cost_usd:
            self.cost.setText(money_text(product.cost_usd))
        self.qty.setFocus()
        self.qty.selectAll()

    def _qty_enter(self) -> None:
        self.cost.setFocus()
        self.cost.selectAll()

    def _pack(self) -> None:
        if self._current is None:
            QMessageBox.information(self, "Compra por empaque", "Primero elija el producto.")
            self.product_input.setFocus()
            return
        d = PackDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted and d.result_qty is not None and d.result_cost is not None:
            self.qty.setText(decimal_field_text(d.result_qty, 3, strip=True))
            self.cost.setText(money_text(d.result_cost))
            self.cost.setFocus()

    def _add_line(self) -> None:
        if self._current is None:
            self.product_input.setFocus()
            return

        def build() -> _Line:
            qty = read_decimal(self.qty, "Cantidad")
            cost = read_decimal(self.cost, "Costo unitario")
            line = _Line(self._current, qty, cost)  # type: ignore[arg-type]
            _ = line.total  # valida cantidad y costo
            return line

        line = run_action(self, build, "Revise el renglón")
        if line is None:
            return
        self.lines.append(line)
        self._current = None
        for w in (self.product_input, self.qty, self.cost):
            w.clear()
        self.product_label.setText("—")
        self._refresh_table()
        self.product_input.setFocus()

    def _remove_line(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.lines):
            del self.lines[row]
            self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.lines))
        for row, line in enumerate(self.lines):
            p = line.product
            values = [
                (p.code, False),
                (p.name, False),
                (format_qty(line.qty, p.allows_fraction) + " " + UNIT_SHORT[Unit(p.unit)], True),
                (format_usd(line.unit_cost, 4), True),
                (format_usd(line.total), True),
            ]
            for col, (text, right) in enumerate(values):
                self.table.setItem(row, col, _item(text, right))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        total = sum((line.total for line in self.lines), ZERO)
        self.total_label.setText(f"Total: {format_usd(total)}")

    # ------------------------------------------------------------------ guardar

    def _save(self) -> None:
        if self.supplier.currentData() is None:
            QMessageBox.warning(self, "Falta el proveedor", "Elija el proveedor o cree uno nuevo.")
            self.supplier.setFocus()
            return
        if not self.lines:
            QMessageBox.warning(self, "Compra vacía", "Agregue al menos un producto.")
            self.product_input.setFocus()
            return
        purchase = run_action(
            self,
            lambda: purchase_service.register_purchase(
                self._conn,
                self._user,
                self.supplier.currentData(),
                [PurchaseLineInput(line.product.id, line.qty, line.unit_cost) for line in self.lines],
                _pydate(self.date.date()),
                self.invoice.text(),
                self.notes.text(),
            ),
        )
        if purchase is not None:
            self.saved_id = purchase.id
            self.accept()

    def reject(self) -> None:
        if self.lines and (
            QMessageBox.question(self, "Cancelar compra", "¿Descartar esta compra sin guardar?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        super().reject()


# ------------------------------------------------------------------ detalle


class PurchaseDetailDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, purchase_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        p = purchase_service.get_purchase(conn, user, purchase_id)
        self.setWindowTitle(f"Compra del {format_date(p.purchase_date)} — {p.supplier_name}")
        self.resize(820, 460)
        info = QLabel(
            f"<b>{p.supplier_name}</b> · Factura: {p.supplier_invoice or '—'} · Fecha: {format_date(p.purchase_date)}"
            f" · Total: <b>{format_usd(p.total_usd)}</b>"
            + (
                f"<br><span style='color:#b00020'>ANULADA el {format_date(p.voided_at)}: {p.void_reason}</span>"
                if p.voided and p.voided_at
                else ""
            )
            + (f"<br>Notas: {p.notes}" if p.notes else "")
        )
        info.setWordWrap(True)
        table = QTableWidget(len(p.items), 5)
        table.setHorizontalHeaderLabels(["Código", "Producto", "Cantidad", "Costo unit. USD", "Total USD"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, it in enumerate(p.items):
            for col, (text, right) in enumerate(
                [
                    (it.product_code, False),
                    (it.product_name, False),
                    (decimal_field_text(it.qty, 3, strip=True), True),
                    (format_usd(it.unit_cost, 4), True),
                    (format_usd(it.line_total), True),
                ]
            ):
                table.setItem(row, col, _item(text, right))
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(table, 1)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)


# ------------------------------------------------------------------ lista


class PurchasesWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Compras")
        self.resize(1000, 600)

        today = date.today()
        self.date_from = QDateEdit(_qdate(today.replace(day=1)))
        self.date_to = QDateEdit(_qdate(today))
        for d in (self.date_from, self.date_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(lambda _: self.refresh())
        self.supplier = QComboBox()
        self.supplier.addItem("Todos los proveedores", None)
        for s in purchase_service.list_suppliers(conn):
            self.supplier.addItem(s.name, s.id)
        self.supplier.currentIndexChanged.connect(lambda _: self.refresh())
        self._product_id: int | None = None
        self.product_button = QPushButton("Filtrar por producto…")
        self.product_button.clicked.connect(self._filter_product)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Desde:"))
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("Hasta:"))
        filters.addWidget(self.date_to)
        filters.addWidget(self.supplier, 1)
        filters.addWidget(self.product_button)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Fecha", "Proveedor", "Factura", "Total USD", "Estado"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self._detail())
        self.summary = QLabel()

        new = QPushButton("Nueva compra (Ctrl+N)")
        detail = QPushButton("Ver detalle (Enter)")
        void = QPushButton("Anular compra…")
        close = QPushButton("Cerrar")
        new.clicked.connect(self._new)
        detail.clicked.connect(self._detail)
        void.clicked.connect(self._void)
        close.clicked.connect(self.accept)
        _no_default(new, detail, void, close, self.product_button)
        buttons = QHBoxLayout()
        buttons.addWidget(self.summary, 1)
        for b in (new, detail, void, close):
            buttons.addWidget(b)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new)
        enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self.table, activated=self._detail)
        enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.purchases: list = []
        self.refresh()

    def refresh(self) -> None:
        self.purchases = purchase_service.list_purchases(
            self._conn,
            self._user,
            _pydate(self.date_from.date()),
            _pydate(self.date_to.date()),
            self.supplier.currentData(),
            self._product_id,
        )
        self.table.setRowCount(len(self.purchases))
        total = ZERO
        for row, p in enumerate(self.purchases):
            if not p.voided:
                total += p.total_usd
            for col, (text, right) in enumerate(
                [
                    (format_date(p.purchase_date), False),
                    (p.supplier_name, False),
                    (p.supplier_invoice, False),
                    (format_usd(p.total_usd), True),
                    ("ANULADA" if p.voided else "Registrada", False),
                ]
            ):
                item = _item(text, right)
                if p.voided:
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        n = sum(1 for p in self.purchases if not p.voided)
        self.summary.setText(f"{n} compra{'s' if n != 1 else ''} · total {format_usd(total)} (sin anuladas)")

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self.purchases[row].id if 0 <= row < len(self.purchases) else None

    def _filter_product(self) -> None:
        if self._product_id is not None:
            self._product_id = None
            self.product_button.setText("Filtrar por producto…")
        else:
            product = resolve_product(self._conn, self._user, "", self)
            if product is None:
                return
            self._product_id = product.id
            self.product_button.setText(f"Producto: {product.code} (quitar)")
        self.refresh()

    def _new(self) -> None:
        d = PurchaseDialog(self._conn, self._user, self)
        if d.exec() == QDialog.DialogCode.Accepted:
            if _pydate(self.date_to.date()) < date.today():
                self.date_to.setDate(_qdate(date.today()))
            self.refresh()

    def _detail(self) -> None:
        pid = self._selected_id()
        if pid is not None:
            PurchaseDetailDialog(self._conn, self._user, pid, self).exec()

    def _void(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        p = next(x for x in self.purchases if x.id == pid)
        if p.voided:
            QMessageBox.information(self, "Anular compra", "Esta compra ya está anulada.")
            return
        reason, ok = QInputDialog.getText(
            self,
            "Anular compra",
            f"Se restarán del inventario los productos de la compra a {p.supplier_name}"
            f" ({format_usd(p.total_usd)}).\nEl costo promedio no se recalcula.\n\nMotivo:",
        )
        if ok:
            run_action(self, lambda: purchase_service.void_purchase(self._conn, self._user, pid, reason))
            self.refresh()
