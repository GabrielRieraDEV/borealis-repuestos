"""Ficha de producto (RF-10, RF-11, RF-13).

Carga rápida: Ctrl+Enter guarda y abre otra ficha conservando categoría, marca y estante; el foco vuelve al nombre.
Enter pasa al campo siguiente (el lector de códigos de barras termina en Enter).
El vendedor ve la ficha de solo lectura y sin costo.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.inventory import MOVEMENT_LABELS
from repuestos.domain.money import hu
from repuestos.domain.pricing import unit_price_ves
from repuestos.domain.products import UNIT_LABELS, UNIT_SHORT, Product, ProductData, Unit
from repuestos.domain.users import User
from repuestos.services import category_service, inventory_service, product_service, rate_service, settings_service
from repuestos.ui.common import EnterMovesFocusDialog, format_qty, read_decimal, run_action
from repuestos.ui.formatting import format_date, format_number, format_usd, format_ves, parse_decimal

FRACTION_UNITS = {Unit.METRO, Unit.LITRO}


def money_text(value: Decimal) -> str:
    """'12,50' o '1,2345': hasta 4 decimales, al menos 2."""
    text = format_number(hu(value, 4), 4)
    while text.endswith("0") and len(text.split(",")[1]) > 2:
        text = text[:-1]
    return text


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fill_row(table: QTableWidget, row: int, values: list[tuple[str, bool]]) -> None:
    for col, (text, right) in enumerate(values):
        item = QTableWidgetItem(text)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)


class ProductDialog(EnterMovesFocusDialog):
    saved = Signal(int)  # id del producto guardado

    def __init__(
        self,
        conn: sqlite3.Connection,
        user: User,
        product_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._product_id = product_id
        self._read_only = not user.is_owner
        settings = settings_service.load(conn)
        self._multiple = settings.rounding_multiple
        rate = rate_service.current_rate(conn)
        self._rate = rate.rate if rate else None

        self.setMinimumWidth(620)
        self._build(settings.default_min_stock)
        if product_id is not None:
            self._load(product_id)
            if self.tabs is not None:
                self._load_history(product_id)
        self._set_title()
        if self._read_only:
            self._make_read_only()
        self.name.setFocus()

    # ------------------------------------------------------------------ construcción

    def _build(self, default_min: Decimal) -> None:
        self.code_label = QLabel("(se asigna al guardar)")
        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("Escanee o escriba (opcional)")
        self.name = QLineEdit()
        self.brand = QLineEdit()
        self.models = QLineEdit()
        self.models.setPlaceholderText("Ej.: Bera 150, Empire Owen 150")
        self.category = QComboBox()
        self.category.addItem("(sin categoría)", None)
        for c in category_service.list_categories(self._conn):
            self.category.addItem(c.name, c.id)
        self.location = QLineEdit()
        self.unit = QComboBox()
        for unit, label in UNIT_LABELS.items():
            self.unit.addItem(label, unit.value)
        self.unit.currentIndexChanged.connect(self._unit_changed)
        self.allows_fraction = QCheckBox("Se vende por fracción (ej. 2,5 m)")
        self.price = QLineEdit()
        self.price.setPlaceholderText("Con IVA incluido")
        self.price.textChanged.connect(self._update_price_ves)
        self.price_ves = QLabel()
        self.cost = QLineEdit()
        self.min_stock = QLineEdit(format_number(default_min, 0))
        self.initial_stock = QLineEdit()
        self.initial_stock.setPlaceholderText("0")
        self.stock_label = QLabel()
        self.status = QLabel()
        self.status.setStyleSheet("color: #1b5e20;")

        form = QFormLayout()
        form.addRow("Código:", self.code_label)
        form.addRow("Nombre:", self.name)
        form.addRow("Código de barras:", self.barcode)
        form.addRow("Marca del repuesto:", self.brand)
        form.addRow("Modelos de moto:", self.models)
        form.addRow("Categoría:", self.category)
        form.addRow("Estante:", self.location)
        form.addRow("Unidad:", self.unit)
        form.addRow("", self.allows_fraction)
        form.addRow("Precio de venta USD:", self.price)
        form.addRow("", self.price_ves)
        self.cost_row_label = QLabel("Costo USD:")
        form.addRow(self.cost_row_label, self.cost)
        form.addRow("Mínimo (para pedir):", self.min_stock)
        self.initial_label = QLabel("Existencia inicial:")
        form.addRow(self.initial_label, self.initial_stock)
        self.stock_row_label = QLabel("Existencia:")
        form.addRow(self.stock_row_label, self.stock_label)

        self.save_button = QPushButton("Guardar (Ctrl+S)")
        self.save_new_button = QPushButton("Guardar y nuevo (Ctrl+Enter)")
        self.cancel_button = QPushButton("Cerrar (Esc)")
        for b in (self.save_button, self.save_new_button, self.cancel_button):
            b.setAutoDefault(False)
        self.save_button.clicked.connect(lambda: self._save(again=False))
        self.save_new_button.clicked.connect(lambda: self._save(again=True))
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.save_new_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=lambda: self._save(again=False))
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self, activated=lambda: self._save(again=True))

        layout = QVBoxLayout(self)
        self.tabs: QTabWidget | None = None
        if self._product_id is not None and self._user.is_owner:
            data_tab = QWidget()
            data_tab.setLayout(form)
            self.kardex_table = _table(
                ["Fecha", "Movimiento", "Cantidad", "Existencia", "Costo prom. USD", "Usuario", "Documento o motivo"]
            )
            self.history_table = _table(["Fecha", "Proveedor", "Factura", "Cantidad", "Costo unit. USD", "Estado"])
            self.tabs = QTabWidget()
            self.tabs.addTab(data_tab, "Datos")
            self.tabs.addTab(self.kardex_table, "Movimientos")
            self.tabs.addTab(self.history_table, "Historial de compras")
            layout.addWidget(self.tabs)
            self.resize(900, 640)
        else:
            layout.addLayout(form)
        layout.addLayout(buttons)

        is_new = self._product_id is None
        self.initial_label.setVisible(is_new)
        self.initial_stock.setVisible(is_new)
        self.stock_row_label.setVisible(not is_new)
        self.stock_label.setVisible(not is_new)
        self.save_new_button.setVisible(is_new)
        self._update_price_ves()

    def _set_title(self) -> None:
        if self._product_id is None:
            self.setWindowTitle("Nuevo producto")
        else:
            self.setWindowTitle(f"Producto {self.code_label.text()}")

    def _load(self, product_id: int) -> None:
        if self._read_only:
            v = product_service.get_view(self._conn, self._user, product_id)
            code, barcode, name, brand, models = v.code, v.barcode, v.name, v.brand, v.compatible_models
            category_name, location, unit, fraction = v.category_name, v.location, Unit(v.unit), v.allows_fraction
            price, cost, min_stock, stock, active = v.price_usd, None, v.min_stock, v.stock, v.active
            category_id = None
        else:
            p = product_service.get_product(self._conn, self._user, product_id)
            d = p.data
            code, barcode, name, brand, models = p.code, d.barcode, d.name, d.brand, d.compatible_models
            category_name, location, unit, fraction = p.category_name, d.location, d.unit, d.allows_fraction
            price, cost, min_stock, stock, active = d.price_usd, d.cost_usd, d.min_stock, p.stock, p.active
            category_id = d.category_id
        self.code_label.setText(code + ("" if active else "  (INACTIVO)"))
        self.barcode.setText(barcode or "")
        self.name.setText(name)
        self.brand.setText(brand)
        self.models.setText(models)
        index = (
            self.category.findData(category_id) if category_id is not None else self.category.findText(category_name)
        )
        if index < 0 and category_name:  # categoría desactivada: se muestra igual
            self.category.addItem(category_name, category_id)
            index = self.category.count() - 1
        self.category.setCurrentIndex(max(index, 0))
        self.location.setText(location)
        self.unit.setCurrentIndex(self.unit.findData(unit.value))
        self.allows_fraction.setChecked(fraction)
        self.price.setText(money_text(price))
        if cost is not None:
            self.cost.setText(money_text(cost))
        self.min_stock.setText(format_qty(min_stock, fraction))
        self.stock_label.setText(f"{format_qty(stock, fraction)} {UNIT_SHORT[unit]}")

    def _load_history(self, product_id: int) -> None:
        """RF-16: kardex e historial de compras."""
        fraction = self.allows_fraction.isChecked()
        lines = inventory_service.kardex(self._conn, self._user, product_id)
        self.kardex_table.setRowCount(len(lines))
        for row, k in enumerate(lines):
            if k.purchase_id is not None:
                doc = f"Compra a {k.supplier_name}" + (f", factura {k.supplier_invoice}" if k.supplier_invoice else "")
                if k.reason:
                    doc += f" — {k.reason}"
            elif k.sale_number is not None:
                doc = f"NE-{k.sale_number:06d}" + (f" — {k.reason}" if k.reason else "")
            else:
                doc = k.reason
            sign = "+" if k.qty > 0 else "−"
            values = [
                (format_date(k.created_at) + k.created_at[10:16], False),
                (MOVEMENT_LABELS[k.kind], False),
                (sign + format_qty(abs(k.qty), fraction), True),
                (format_qty(k.stock_after, fraction), True),
                (format_usd(k.unit_cost, 4), True),
                (k.user_name, False),
                (doc, False),
            ]
            _fill_row(self.kardex_table, row, values)
        self.kardex_table.resizeColumnsToContents()
        history = inventory_service.purchase_history(self._conn, self._user, product_id)
        self.history_table.setRowCount(len(history))
        for row, h in enumerate(history):
            values = [
                (format_date(h.purchase_date), False),
                (h.supplier_name, False),
                (h.supplier_invoice, False),
                (format_qty(h.qty, fraction), True),
                (format_usd(h.unit_cost, 4), True),
                ("ANULADA" if h.voided else "", False),
            ]
            _fill_row(self.history_table, row, values)
        self.history_table.resizeColumnsToContents()

    def _make_read_only(self) -> None:
        for w in (self.barcode, self.name, self.brand, self.models, self.location, self.price, self.min_stock):
            w.setReadOnly(True)
        for w in (self.category, self.unit, self.allows_fraction):
            w.setEnabled(False)
        for w in (self.cost, self.cost_row_label, self.save_button, self.save_new_button):
            w.setVisible(False)

    # ------------------------------------------------------------------ comportamiento

    def _unit_changed(self) -> None:
        if Unit(self.unit.currentData()) in FRACTION_UNITS:
            self.allows_fraction.setChecked(True)

    def _update_price_ves(self) -> None:
        if self._rate is None:
            self.price_ves.setText("Sin tasa cargada: el precio en Bs se verá al cargar la tasa.")
            return
        try:
            price = parse_decimal(self.price.text())
            self.price_ves.setText(
                f"Con la tasa de hoy: {format_ves(unit_price_ves(price, self._rate, self._multiple))}"
            )
        except (ValueError, ArithmeticError):
            self.price_ves.setText("")

    def _collect(self) -> tuple[ProductData, Decimal]:
        data = ProductData(
            name=self.name.text(),
            brand=self.brand.text(),
            compatible_models=self.models.text(),
            category_id=self.category.currentData(),
            location=self.location.text(),
            unit=Unit(self.unit.currentData()),
            allows_fraction=self.allows_fraction.isChecked(),
            barcode=self.barcode.text(),
            price_usd=read_decimal(self.price, "Precio de venta"),
            cost_usd=read_decimal(self.cost, "Costo", default=Decimal("0")),
            min_stock=read_decimal(self.min_stock, "Mínimo", default=Decimal("0")),
        )
        initial = read_decimal(self.initial_stock, "Existencia inicial", default=Decimal("0"))
        return data, initial

    def _save(self, again: bool) -> None:
        if self._read_only:
            return
        if again and self._product_id is not None:
            again = False

        def action() -> Product:
            data, initial = self._collect()
            if self._product_id is None:
                return product_service.create_product(self._conn, self._user, data, initial)
            return product_service.update_product(self._conn, self._user, self._product_id, data)

        product = run_action(self, action)
        if product is None:
            return
        self.saved.emit(product.id)
        if not again:
            self.accept()
            return
        self._reset_for_next()
        self.status.setText(f"Guardado {product.code} — {product.name}")

    def _reset_for_next(self) -> None:
        """Conserva categoría, marca y estante (RF-11)."""
        for w in (self.barcode, self.name, self.models, self.price, self.cost, self.initial_stock):
            w.clear()
        self.unit.setCurrentIndex(0)
        self.allows_fraction.setChecked(False)
        self.min_stock.setText(format_number(settings_service.load(self._conn).default_min_stock, 0))
        self.name.setFocus()
