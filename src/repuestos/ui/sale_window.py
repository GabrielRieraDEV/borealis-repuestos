"""Pantalla de venta (RF-50 a RF-52, RF-54), operable solo con teclado.

F2 buscar · escanear agrega directo · Enter agrega · F4 cambia cantidad · Supr quita · F3 cliente
· F9 cobrar · Esc cancelar.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.db.repositories.customers import Customer
from repuestos.domain.money import ZERO
from repuestos.domain.pricing import compute_change, credit_debt_usd, ves_equivalent
from repuestos.domain.products import UNIT_SHORT, Unit
from repuestos.domain.sale import (
    METHOD_CURRENCY,
    METHOD_LABELS,
    PaymentInput,
    PaymentMethod,
    check_payment,
    payment_summary,
)
from repuestos.domain.users import User
from repuestos.formatting import format_date, format_number, format_rate, format_usd, format_ves, parse_decimal
from repuestos.services import (
    cash_service,
    customer_service,
    print_service,
    product_service,
    rate_service,
    sale_service,
    settings_service,
)
from repuestos.services.sale_service import (
    CartItem,
    CreditLimitError,
    InsufficientStockError,
    LineQuote,
    RateChangedError,
)
from repuestos.ui.authorize_dialog import ask_owner_authorization
from repuestos.ui.common import decimal_field_text, format_qty, read_decimal, run_action
from repuestos.ui.print_helpers import print_with_fallback
from repuestos.ui.product_picker import resolve_product


def _no_default(*buttons: QPushButton) -> None:
    for b in buttons:
        b.setAutoDefault(False)
        b.setDefault(False)


def _cell(text: str, right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


# ------------------------------------------------------------------ cliente (RF-51)


class CustomerDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.customer: Customer | None = None
        self.setWindowTitle("Cliente")
        self.resize(560, 460)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cédula, RIF o nombre y Enter")
        self.results = QListWidget()
        self.id_doc = QLineEdit()
        self.id_doc.setPlaceholderText("V12345678")
        self.name = QLineEdit()
        self.phone = QLineEdit()
        create = QPushButton("Crear cliente")
        final = QPushButton("Consumidor final (F12)")
        _no_default(create, final)
        form = QFormLayout()
        form.addRow("Cédula / RIF:", self.id_doc)
        form.addRow("Nombre:", self.name)
        form.addRow("Teléfono:", self.phone)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Buscar cliente:"))
        layout.addWidget(self.search)
        layout.addWidget(self.results, 1)
        layout.addWidget(QLabel("<b>Cliente nuevo</b>"))
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addWidget(create)
        buttons.addStretch(1)
        buttons.addWidget(final)
        layout.addLayout(buttons)

        self.search.returnPressed.connect(self._search)
        self.results.itemActivated.connect(self._choose)
        self.id_doc.returnPressed.connect(self.name.setFocus)
        self.name.returnPressed.connect(self.phone.setFocus)
        self.phone.returnPressed.connect(self._create)
        create.clicked.connect(self._create)
        final.clicked.connect(self._final)
        QShortcut(QKeySequence("F12"), self, activated=self._final)
        self.search.setFocus()

    def _search(self) -> None:
        self.results.clear()
        found = customer_service.search(self._conn, self.search.text())
        for c in found:
            item = QListWidgetItem(f"{customer_service.format_id_doc(c.id_doc)}  —  {c.name}")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self.results.addItem(item)
        if found:
            self.results.setCurrentRow(0)
            self.results.setFocus()
        else:
            self.id_doc.setText(self.search.text() if any(ch.isdigit() for ch in self.search.text()) else "")
            if not self.id_doc.text():
                self.name.setText(self.search.text())
            (self.name if self.id_doc.text() else self.id_doc).setFocus()

    def _choose(self, item: QListWidgetItem) -> None:
        self.customer = customer_service.get(self._conn, item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    def _create(self) -> None:
        c = run_action(
            self,
            lambda: customer_service.create(
                self._conn, self._user, self.name.text(), self.id_doc.text(), self.phone.text()
            ),
        )
        if c is not None:
            self.customer = c
            self.accept()

    def _final(self) -> None:
        self.customer = customer_service.final_consumer(self._conn)
        self.accept()


# ------------------------------------------------------------------ cobro (RF-52, RN-06)


class PaymentDialog(QDialog):
    """F1 Efectivo Bs · F2 Efectivo USD · F3 Punto · F4 Pago móvil · F5 USDT · Enter agrega/cobra · Supr quita."""

    KEYS = {
        PaymentMethod.CASH_VES: "F1",
        PaymentMethod.CASH_USD: "F2",
        PaymentMethod.POS: "F3",
        PaymentMethod.MOBILE: "F4",
        PaymentMethod.USDT: "F5",
        PaymentMethod.CREDIT: "F6",
    }

    def __init__(
        self,
        total_ves: Decimal,
        total_usd: Decimal,
        rate: Decimal,
        usdt_enabled: bool,
        parent: QWidget | None = None,
        credit_customer: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.total_ves = total_ves
        self.rate = rate
        self.payments: list[PaymentInput] = []
        self.change_usd = ZERO
        self.on_credit = False  # el resto va a fiado (RF-71)
        self.credit_customer = credit_customer
        self.setWindowTitle("Cobrar")
        self.resize(760, 560)

        total = QLabel(f"TOTAL {format_ves(total_ves)}")
        total.setStyleSheet("font-size: 24pt; font-weight: bold;")
        ref = QLabel(f"Referencia {format_usd(total_usd)}  ·  Tasa BCV {format_rate(rate)}")

        self.method = QComboBox()
        for m in PaymentMethod:
            if m is PaymentMethod.USDT and not usdt_enabled:
                continue
            self.method.addItem(f"{METHOD_LABELS[m]} ({self.KEYS[m]})", m.value)
        credit_index = self.method.findData(PaymentMethod.CREDIT.value)
        if credit_customer is None:
            self.method.model().item(credit_index).setEnabled(False)
            self.method.setItemData(
                credit_index,
                "El cliente no tiene fiado habilitado. Elija el cliente con F3 en la venta.",
                Qt.ItemDataRole.ToolTipRole,
            )
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("Monto (Enter con el campo vacío completa lo que falta)")
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("Referencia (opcional)")
        add = QPushButton("Agregar (Enter)")
        entry = QHBoxLayout()
        entry.addWidget(self.method)
        entry.addWidget(self.amount, 1)
        entry.addWidget(self.reference)
        entry.addWidget(add)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Forma de pago", "Monto", "Equivale"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.paid_label = QLabel()
        self.due_label = QLabel()
        self.due_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self.change_box = QWidget()
        change_row = QHBoxLayout(self.change_box)
        change_row.setContentsMargins(0, 0, 0, 0)
        self.change_total = QLabel()
        self.change_total.setStyleSheet("font-size: 16pt; font-weight: bold; color: #1b5e20;")
        self.change_usd_input = QLineEdit("0")
        self.change_usd_input.setMaximumWidth(120)
        self.change_rest = QLabel()
        self.change_rest.setStyleSheet("font-size: 14pt;")
        change_row.addWidget(self.change_total)
        change_row.addWidget(QLabel("Entrega en USD:"))
        change_row.addWidget(self.change_usd_input)
        change_row.addWidget(self.change_rest, 1)

        self.charge_button = QPushButton("Cobrar (F9)")
        self.charge_button.setStyleSheet("font-size: 14pt; padding: 8px 24px;")
        cancel = QPushButton("Volver (Esc)")
        _no_default(add, self.charge_button, cancel)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(cancel)
        bottom.addWidget(self.charge_button)

        layout = QVBoxLayout(self)
        layout.addWidget(total)
        layout.addWidget(ref)
        layout.addLayout(entry)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.paid_label)
        layout.addWidget(self.due_label)
        layout.addWidget(self.change_box)
        layout.addLayout(bottom)

        add.clicked.connect(self._enter)
        self.amount.returnPressed.connect(self._enter)
        self.reference.returnPressed.connect(self._enter)
        self.change_usd_input.textChanged.connect(lambda _: self._refresh())
        self.change_usd_input.returnPressed.connect(self._charge)
        self.charge_button.clicked.connect(self._charge)
        cancel.clicked.connect(self.reject)
        QShortcut(QKeySequence("F9"), self, activated=self._charge)
        for m, key in self.KEYS.items():
            if self.method.findData(m.value) >= 0 and (m is not PaymentMethod.CREDIT or credit_customer):
                QShortcut(QKeySequence(key), self, activated=lambda m=m: self._select(m))
        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table, activated=self._remove)
        delete.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._refresh()
        self._select(PaymentMethod.CASH_VES)

    # ------------------------------------------------------------------ cálculo

    def summary(self):
        return payment_summary(self.total_ves, self.payments, self.rate)

    def _due_in(self, method: PaymentMethod) -> Decimal:
        due = self.summary().due_ves
        if METHOD_CURRENCY[method].value == "USD":
            return self.summary().due_usd_ref
        return due

    def _change(self):
        s = self.summary()
        if s.change_ves <= 0:
            return None
        usd = read_decimal(self.change_usd_input, "Vuelto en USD", default=ZERO)
        return compute_change(self.total_ves, s.paid_ves, usd, self.rate)

    def _refresh(self) -> None:
        s = self.summary()
        if s.complete:
            self.on_credit = False
        self.table.setRowCount(len(self.payments) + (1 if self.on_credit else 0))
        for row, p in enumerate(self.payments):
            amount = format_usd(p.amount) if p.currency.value == "USD" else format_ves(p.amount)
            label = METHOD_LABELS[p.method] + (f" · Ref. {p.reference}" if p.reference else "")
            self.table.setItem(row, 0, _cell(label))
            self.table.setItem(row, 1, _cell(amount, True))
            self.table.setItem(row, 2, _cell(format_ves(ves_equivalent(p.amount, p.currency, self.rate)), True))
        if self.on_credit:
            row = len(self.payments)
            self.table.setItem(row, 0, _cell(f"Fiado a {self.credit_customer} (Supr quita)"))
            self.table.setItem(row, 1, _cell(format_usd(credit_debt_usd(s.due_ves, self.rate)), True))
            self.table.setItem(row, 2, _cell(format_ves(s.due_ves), True))
        self.paid_label.setText(f"Pagado: {format_ves(s.paid_ves)}")
        if self.on_credit:
            self.due_label.setText(
                f"A fiado: {format_ves(s.due_ves)}  ·  deuda {format_usd(credit_debt_usd(s.due_ves, self.rate))}"
            )
            self.due_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #8a4b00;")
        elif s.due_ves > 0:
            self.due_label.setText(f"Falta: {format_ves(s.due_ves)}  ·  {format_usd(s.due_usd_ref)}")
            self.due_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #b00020;")
        else:
            self.due_label.setText("Pago completo")
            self.due_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #1b5e20;")
        self.change_box.setVisible(s.change_ves > 0)
        ok = s.complete or (self.on_credit and s.due_ves > 0)
        if s.change_ves > 0:
            self.change_total.setText(f"Vuelto: {format_ves(s.change_ves)}")
            try:
                change = self._change()
                assert change is not None
                self.change_rest.setText(f"→ y en Bs: {format_ves(change.rest_ves)}")
                self.change_rest.setStyleSheet("font-size: 14pt;")
            except ValueError as exc:
                self.change_rest.setText(str(exc))
                self.change_rest.setStyleSheet("font-size: 12pt; color: #b00020;")
                ok = False
        self.charge_button.setEnabled(ok)

    # ------------------------------------------------------------------ acciones

    def _select(self, method: PaymentMethod) -> None:
        index = self.method.findData(method.value)
        if index < 0:
            return
        if method is PaymentMethod.CREDIT:
            self._toggle_credit()
            return
        self.method.setCurrentIndex(index)
        self.amount.clear()
        self.amount.setFocus()

    def _toggle_credit(self) -> None:
        """F6: lo que falta va a fiado; otra vez F6 (o Supr sobre el renglón) lo quita."""
        if self.credit_customer is None or self.summary().complete:
            return
        self.on_credit = not self.on_credit
        self._refresh()
        (self.charge_button if self.on_credit else self.amount).setFocus()

    def _enter(self) -> None:
        method = PaymentMethod(self.method.currentData())
        if method is PaymentMethod.CREDIT:
            self._toggle_credit()
            return
        s = self.summary()
        if not self.amount.text().strip():
            if s.complete:
                self._charge()
                return
            amount = self._due_in(method)
        else:
            try:
                amount = read_decimal(self.amount, "Monto")
            except ValueError as exc:
                QMessageBox.warning(self, "Monto", str(exc))
                return
        payment = PaymentInput(method, amount, self.reference.text().strip())
        if run_action(self, lambda: check_payment(payment) or True, "Monto") is None:
            return
        self.payments.append(payment)
        self.amount.clear()
        self.reference.clear()
        self._refresh()
        if self.summary().complete:
            if self.summary().change_ves > 0:
                self.change_usd_input.setFocus()
                self.change_usd_input.selectAll()
            else:
                self.charge_button.setFocus()
        else:
            self.amount.setFocus()

    def _remove(self) -> None:
        row = self.table.currentRow()
        if self.on_credit and row == len(self.payments):
            self._toggle_credit()
            return
        if 0 <= row < len(self.payments):
            del self.payments[row]
            self._refresh()

    def _charge(self) -> None:
        self._refresh()
        if not self.charge_button.isEnabled():
            return
        change = self._change()
        self.change_usd = change.usd if change else ZERO
        self.accept()


# ------------------------------------------------------------------ venta


class SaleWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.lines: list[LineQuote] = []
        self.customer = customer_service.final_consumer(conn)
        current = rate_service.require_rate(conn)
        self.rate = current.rate
        self.rate_date = current.valid_date
        self.last_sale_id: int | None = None
        self.setWindowTitle("Vender")
        self.resize(1250, 760)

        self.customer_label = QLabel()
        self.customer_label.setStyleSheet("font-size: 13pt;")
        self.rate_label = QLabel()
        seller = QLabel(f"Vendedor: {user.full_name}")
        top = QHBoxLayout()
        top.addWidget(self.customer_label, 1)
        top.addWidget(self.rate_label)
        top.addWidget(seller)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Escanee o escriba el producto y pulse Enter (F2)")
        self.search.setStyleSheet("font-size: 14pt; padding: 4px;")
        self.qty = QLineEdit("1")
        self.qty.setMaximumWidth(100)
        self.qty.setStyleSheet("font-size: 14pt; padding: 4px;")
        self.selected_label = QLabel()
        entry = QHBoxLayout()
        entry.addWidget(self.search, 1)
        entry.addWidget(QLabel("Cant.:"))
        entry.addWidget(self.qty)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Código", "Descripción", "Cantidad", "Precio Bs", "Total Bs", "Ref. USD"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("font-size: 13pt;")

        self.base_label = QLabel()
        self.vat_label = QLabel()
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 28pt; font-weight: bold;")
        self.usd_label = QLabel()
        self.usd_label.setStyleSheet("font-size: 15pt;")
        totals = QGridLayout()
        totals.addWidget(self.base_label, 0, 0)
        totals.addWidget(self.vat_label, 1, 0)
        totals.addWidget(self.total_label, 0, 1, 2, 1, Qt.AlignmentFlag.AlignRight)
        totals.addWidget(self.usd_label, 2, 1, Qt.AlignmentFlag.AlignRight)
        self.last_label = QLabel()
        self.last_label.setStyleSheet("color: #1b5e20;")
        hints = QLabel(
            "F2 buscar · Enter agregar · ↑↓ elegir renglón · F4 cantidad · Supr quitar · F3 cliente · "
            "F9 cobrar · Esc cancelar"
        )
        hints.setStyleSheet("color: #555;")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(entry)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(totals)
        layout.addWidget(self.last_label)
        layout.addWidget(hints)

        self._pending = None  # producto elegido esperando cantidad
        self.search.returnPressed.connect(self._search_enter)
        self.qty.returnPressed.connect(self._qty_enter)
        self.search.installEventFilter(self)
        self.table.installEventFilter(self)
        QShortcut(QKeySequence("F2"), self, activated=self._focus_search)
        QShortcut(QKeySequence("F3"), self, activated=self._choose_customer)
        QShortcut(QKeySequence("F4"), self, activated=self._change_qty)
        QShortcut(QKeySequence("F9"), self, activated=self._charge)
        self._refresh()
        self.search.setFocus()

    # ------------------------------------------------------------------ teclado

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            key = event.key()
            if obj is self.search and key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self.lines:
                row = self.table.currentRow()
                row = (
                    (row + (1 if key == Qt.Key.Key_Down else -1)) % len(self.lines) if row >= 0 else len(self.lines) - 1
                )
                self.table.selectRow(row)
                return True
            if key == Qt.Key.Key_Delete and (obj is self.table or (obj is self.search and not self.search.text())):
                self._remove_selected()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return  # Enter solo lo manejan los campos
        super().keyPressEvent(event)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # ------------------------------------------------------------------ renglones

    def _read_qty(self) -> Decimal | None:
        try:
            return read_decimal(self.qty, "Cantidad", default=Decimal(1))
        except ValueError as exc:
            QMessageBox.warning(self, "Cantidad", str(exc))
            return None

    def _search_enter(self) -> None:
        text = self.search.text().strip()
        if not text:
            return
        scanned = product_service.find_by_scan(self._conn, self._user, text)
        if scanned is not None:  # el lector de códigos: agrega directo
            qty = self._read_qty()
            if qty is not None:
                self._add(scanned.id, qty)
            return
        product = resolve_product(self._conn, self._user, text, self)
        if product is None:
            self._focus_search()
            return
        if not product.active:
            QMessageBox.warning(self, "Producto inactivo", "Ese producto está inactivo y no se puede vender.")
            return
        self._pending = product
        unit = UNIT_SHORT[Unit(product.unit)]
        self.selected_label.setText(
            f"{product.code} — {product.name} · hay {format_qty(product.stock, product.allows_fraction)} {unit}"
            f" · {format_ves(product.price_ves) if product.price_ves else ''}  → escriba la cantidad y Enter"
        )
        self.search.setText(product.name)
        self.qty.setFocus()
        self.qty.selectAll()

    def _qty_enter(self) -> None:
        if self._pending is None:
            self._search_enter()
            return
        qty = self._read_qty()
        if qty is not None:
            self._add(self._pending.id, qty)

    def _add(self, product_id: int, qty: Decimal) -> None:
        existing = next((i for i, q in enumerate(self.lines) if q.product_id == product_id), None)
        new_qty = qty + (self.lines[existing].qty if existing is not None else ZERO)
        quote = run_action(
            self, lambda: sale_service.quote_line(self._conn, product_id, new_qty, self.rate), "Cantidad"
        )
        if quote is None:
            return
        if quote.stock - new_qty < 0:
            self.selected_label.setText(
                f"⚠ {quote.code} — {quote.description}: hay {format_qty(quote.stock, quote.allows_fraction)}."
                " Al cobrar se pedirá la clave de la dueña."
            )
        else:
            self.selected_label.setText("")
        if existing is None:
            self.lines.append(quote)
            row = len(self.lines) - 1
        else:
            self.lines[existing] = quote
            row = existing
        self._pending = None
        self.search.clear()
        self.qty.setText("1")
        self._refresh()
        self.table.selectRow(row)
        self.search.setFocus()

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.lines):
            del self.lines[row]
            self._refresh()
            if self.lines:
                self.table.selectRow(min(row, len(self.lines) - 1))

    def _change_qty(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.lines):
            return
        q = self.lines[row]
        text, ok = QInputDialog.getText(
            self, "Cantidad", f"Cantidad de {q.description}:", text=decimal_field_text(q.qty, 3, strip=True)
        )
        if not ok:
            return
        try:
            new_qty = parse_decimal(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Cantidad", str(exc))
            return
        if new_qty == 0:
            self._remove_selected()
            return
        quote = run_action(
            self, lambda: sale_service.quote_line(self._conn, q.product_id, new_qty, self.rate), "Cantidad"
        )
        if quote is not None:
            self.lines[row] = quote
            self._refresh()
            self.table.selectRow(row)
        self.search.setFocus()

    def _requote_all(self) -> None:
        self.lines = [sale_service.quote_line(self._conn, q.product_id, q.qty, self.rate) for q in self.lines]

    def _refresh(self) -> None:
        doc = self.customer.id_doc
        self.customer_label.setText(
            f"Cliente: <b>{self.customer.name}</b>"
            + (f" ({customer_service.format_id_doc(doc)})" if doc else "")
            + "  <span style='color:#555'>(F3 cambiar)</span>"
        )
        self.rate_label.setText(f"Tasa BCV {format_rate(self.rate)} ({format_date(self.rate_date)})")
        self.table.setRowCount(len(self.lines))
        for row, q in enumerate(self.lines):
            unit = UNIT_SHORT[Unit(q.unit)]
            values = [
                (q.code, False),
                (q.description, False),
                (f"{format_qty(q.qty, q.allows_fraction)} {unit}", True),
                (format_number(q.unit_price_ves, 2), True),
                (format_number(q.line_total_ves, 2), True),
                (format_number(q.line_total_usd, 2), True),
            ]
            for col, (text, right) in enumerate(values):
                self.table.setItem(row, col, _cell(text, right))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        t = sale_service.totals(self.lines)
        self.base_label.setText(f"Base imponible: {format_ves(t.ves.base)}")
        self.vat_label.setText(f"IVA 16 %: {format_ves(t.ves.vat)}")
        self.total_label.setText(f"TOTAL {format_ves(t.ves.total)}")
        self.usd_label.setText(f"Referencia {format_usd(t.usd.total)}")

    # ------------------------------------------------------------------ cliente, cancelar, cobrar

    def _choose_customer(self) -> None:
        d = CustomerDialog(self._conn, self._user, self)
        if d.exec() == QDialog.DialogCode.Accepted and d.customer is not None:
            self.customer = d.customer
            self._refresh()
        self.search.setFocus()

    def _reset(self) -> None:
        self.lines = []
        self._pending = None
        self.customer = customer_service.final_consumer(self._conn)
        self.search.clear()
        self.qty.setText("1")
        self.selected_label.setText("")
        self._refresh()
        self.search.setFocus()

    def _cancel(self) -> None:
        if not self.lines:
            self.reject()
            return
        if QMessageBox.question(self, "Cancelar venta", "¿Cancelar esta venta?") == QMessageBox.StandardButton.Yes:
            self._reset()

    def _check_rate(self) -> bool:
        """Si la tasa cambió (descarga automática), recalcula los precios antes de cobrar."""
        current = rate_service.current_rate(self._conn)
        if current is None:
            QMessageBox.warning(self, "Sin tasa", "No hay tasa del día. Cárguela en Tasa BCV.")
            return False
        if current.rate != self.rate:
            self.rate, self.rate_date = current.rate, current.valid_date
            self._requote_all()
            self._refresh()
            QMessageBox.information(
                self, "Tasa nueva", f"La tasa cambió a {format_rate(self.rate)}. Se actualizaron los precios."
            )
            return False
        return True

    def _charge(self) -> None:
        if not self.lines:
            self.search.setFocus()
            return
        if cash_service.current_session(self._conn) is None:
            QMessageBox.warning(self, "Caja cerrada", cash_service.NO_OPEN_SESSION)
            return
        if not self._check_rate():
            return
        t = sale_service.totals(self.lines)
        usdt = settings_service.load(self._conn).payment_usdt_enabled
        credit_name = (
            self.customer.name if self.customer.credit_enabled and not self.customer.is_final_consumer else None
        )
        pay = PaymentDialog(t.ves.total, t.usd.total, self.rate, usdt, self, credit_customer=credit_name)
        if pay.exec() != QDialog.DialogCode.Accepted:
            self.search.setFocus()
            return
        items = [CartItem(q.product_id, q.qty) for q in self.lines]
        authorized_by: int | None = None
        while True:
            try:
                sale = sale_service.charge(
                    self._conn,
                    self._user,
                    items,
                    pay.payments,
                    self.rate,
                    self.customer.id,
                    pay.change_usd,
                    authorized_by,
                    on_credit=pay.on_credit,
                )
                break
            except CreditLimitError as exc:
                if (
                    QMessageBox.question(self, "Límite de fiado", f"{exc}\n\n¿Fiar igual?")
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                authorized_by = ask_owner_authorization(self._conn, self._user, "fiar por encima del límite", self)
                if authorized_by is None:
                    return
            except InsufficientStockError as exc:
                if (
                    QMessageBox.question(self, "Sin existencia suficiente", f"{exc}\n\n¿Vender igual?")
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                authorized_by = ask_owner_authorization(self._conn, self._user, "vender sin existencia", self)
                if authorized_by is None:
                    return
            except RateChangedError:
                self._check_rate()
                return
            except (ValueError, LookupError, PermissionError) as exc:
                QMessageBox.warning(self, "No se pudo cobrar", str(exc))
                return
        self.last_sale_id = sale.id
        change = [p for p in sale.payments if p.is_change]
        change_text = (
            " · vuelto "
            + " + ".join(format_usd(-p.amount) if p.currency.value == "USD" else format_ves(-p.amount) for p in change)
            if change
            else ""
        )
        self.last_label.setText(f"Última venta {sale.doc_number} · {format_ves(sale.total_ves)}{change_text}")
        self._reset()
        print_with_fallback(
            self,
            lambda: print_service.print_sale(self._conn, self._user, sale.id),
            lambda: print_service.save_sale_pdf(self._conn, self._user, sale.id),
        )
        self.search.setFocus()
