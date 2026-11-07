"""Fiado (RF-70 a RF-73): deudores, clientes, estado de cuenta, abonos y su anulación."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.money import ZERO
from repuestos.domain.sale import METHOD_LABELS, PaymentMethod
from repuestos.domain.users import User
from repuestos.formatting import format_date, format_rate, format_usd
from repuestos.services import credit_service, customer_service, print_service, rate_service, settings_service
from repuestos.ui.common import decimal_field_text, read_decimal, run_action
from repuestos.ui.print_helpers import print_with_fallback

OVERDUE = QBrush(QColor("#b00020"))
MUTED = QBrush(QColor("#9e9e9e"))


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    return t


def _fill(t: QTableWidget, row: int, values: list[tuple[str, bool]], brush: QBrush | None = None) -> None:
    for col, (text, right) in enumerate(values):
        item = QTableWidgetItem(text)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if brush is not None:
            item.setForeground(brush)
        t.setItem(row, col, item)


def _button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setAutoDefault(False)
    return b


# ------------------------------------------------------------------ abono (RF-72)


class CreditPaymentDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, customer_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._customer_id = customer_id
        self.saved_id: int | None = None
        customer = customer_service.get(conn, customer_id)
        balance = credit_service.customer_balance(conn, customer_id)
        rate = rate_service.require_rate(conn)
        self.setWindowTitle(f"Registrar abono — {customer.name}")
        self.setMinimumWidth(520)

        info = QLabel(
            f"<b>{customer.name}</b> debe <b>{format_usd(balance)}</b><br>"
            f"Tasa BCV de hoy: {format_rate(rate.rate)}. Los abonos en Bs se convierten a USD con esta tasa."
        )
        info.setWordWrap(True)
        self.method = QComboBox()
        usdt = settings_service.load(conn).payment_usdt_enabled
        for m in PaymentMethod:
            if m is PaymentMethod.CREDIT or (m is PaymentMethod.USDT and not usdt):
                continue
            self.method.addItem(METHOD_LABELS[m], m.value)
        self.amount = QLineEdit()
        self.reference = QLineEdit()
        self.preview = QLabel()
        self.preview.setStyleSheet("font-size: 13pt;")
        form = QFormLayout()
        form.addRow("Forma de pago:", self.method)
        form.addRow("Monto:", self.amount)
        form.addRow("Referencia:", self.reference)
        save = _button("Guardar abono")
        cancel = _button("Cancelar")
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(self.preview)
        layout.addLayout(buttons)
        self.method.currentIndexChanged.connect(lambda _: self._update())
        self.amount.textChanged.connect(lambda _: self._update())
        self.amount.returnPressed.connect(self.reference.setFocus)
        self.reference.returnPressed.connect(self._save)
        self.amount.setFocus()

    def _update(self) -> None:
        try:
            amount = read_decimal(self.amount, "Monto")
            p = credit_service.preview_payment(
                self._conn, self._customer_id, PaymentMethod(self.method.currentData()), amount
            )
        except (ValueError, LookupError, ArithmeticError):
            self.preview.setText("")
            return
        if p.balance_after < 0:
            self.preview.setText(
                f"Abona {format_usd(p.amount_usd)}: es más que la deuda ({format_usd(p.balance_before)})."
            )
            self.preview.setStyleSheet("font-size: 13pt; color: #b00020;")
        else:
            self.preview.setText(f"Abona {format_usd(p.amount_usd)} · el saldo queda en {format_usd(p.balance_after)}")
            self.preview.setStyleSheet("font-size: 13pt; color: #1b5e20;")

    def _save(self) -> None:
        payment = run_action(
            self,
            lambda: credit_service.register_payment(
                self._conn,
                self._user,
                self._customer_id,
                PaymentMethod(self.method.currentData()),
                read_decimal(self.amount, "Monto"),
                self.reference.text(),
            ),
            "No se pudo guardar el abono",
        )
        if payment is None:
            return
        self.saved_id = payment.id
        self.accept()
        print_with_fallback(
            self.parentWidget(),
            lambda: print_service.print_credit_receipt(self._conn, payment.id),
            lambda: print_service.save_credit_receipt_pdf(self._conn, payment.id),
        )


def register_payment_flow(conn: sqlite3.Connection, user: User, customer_id: int, parent: QWidget | None) -> bool:
    from repuestos.services import cash_service

    if cash_service.current_session(conn) is None:
        QMessageBox.warning(parent, "Caja cerrada", "Para registrar un abono la caja debe estar abierta.")
        return False
    if rate_service.current_rate(conn) is None:
        QMessageBox.warning(parent, "Sin tasa", "No hay tasa del día. Cárguela en Tasa BCV.")
        return False
    if credit_service.customer_balance(conn, customer_id) <= 0:
        QMessageBox.information(parent, "Abono", "Este cliente no tiene deudas pendientes.")
        return False
    return CreditPaymentDialog(conn, user, customer_id, parent).exec() == QDialog.DialogCode.Accepted


# ------------------------------------------------------------------ estado de cuenta (RF-73)


class StatementDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, customer_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._customer_id = customer_id
        self.resize(900, 620)
        self.header = QLabel()
        self.header.setWordWrap(True)
        self.header.setStyleSheet("font-size: 13pt;")
        self.debts = _table(["Nota", "Fecha", "Monto USD", "Saldo USD", "Vence", "Estado"])
        self.payments = _table(["Abono", "Fecha", "USD", "Tasa", "Aplicado a", "Recibió", "Estado"])
        pay = _button("Registrar abono")
        reprint = _button("Reimprimir abono")
        void = _button("Anular abono…")
        void.setVisible(user.is_owner)
        close = _button("Cerrar")
        pay.clicked.connect(self._pay)
        reprint.clicked.connect(self._reprint)
        void.clicked.connect(self._void)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        for b in (pay, reprint, void):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(QLabel("<b>Deudas</b>"))
        layout.addWidget(self.debts, 3)
        layout.addWidget(QLabel("<b>Abonos</b>"))
        layout.addWidget(self.payments, 2)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        st = credit_service.statement(self._conn, self._customer_id)
        c = st.customer
        self.setWindowTitle(f"Estado de cuenta — {c.name}")
        limit = format_usd(c.credit_limit_usd) if c.credit_limit_usd is not None else "sin límite"
        overdue = (
            f" · <span style='color:#b00020'>vencido {format_usd(st.overdue_usd)}</span>" if st.overdue_usd else ""
        )
        self.header.setText(
            f"<b>{c.name}</b> {customer_service.format_id_doc(c.id_doc)} · Tel. {c.phone or '—'}<br>"
            f"Debe <b>{format_usd(st.balance_usd)}</b>{overdue} · límite {limit}"
            f" · fiado {'habilitado' if c.credit_enabled else 'NO habilitado'}"
        )
        self.debts.setRowCount(len(st.debts))
        for row, d in enumerate(st.debts):
            r = d.receivable
            status = {"OPEN": "Pendiente", "PAID": "Pagada", "VOIDED": "Anulada"}[r.status]
            if d.overdue:
                status = "VENCIDA"
            brush = OVERDUE if d.overdue else MUTED if r.status != "OPEN" else None
            _fill(
                self.debts,
                row,
                [
                    (r.doc_number, False),
                    (format_date(r.created_at), False),
                    (format_usd(r.amount_usd), True),
                    (format_usd(r.balance_usd), True),
                    (format_date(r.due_date), False),
                    (status, False),
                ],
                brush,
            )
        self.debts.resizeColumnsToContents()
        self._payments = st.payments
        self.payments.setRowCount(len(st.payments))
        for row, p in enumerate(st.payments):
            applied = ", ".join(f"NE-{a.sale_number:06d} ({format_usd(a.amount_usd)})" for a in p.allocations)
            _fill(
                self.payments,
                row,
                [
                    (p.doc_number, False),
                    (f"{format_date(p.created_at)} {p.created_at[11:16]}", False),
                    (format_usd(p.amount_usd), True),
                    (format_rate(p.rate), True),
                    (applied, False),
                    (p.user_name, False),
                    ("ANULADO" if p.voided else "", False),
                ],
                MUTED if p.voided else None,
            )
        self.payments.resizeColumnsToContents()
        self.payments.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _selected_payment(self):
        row = self.payments.currentRow()
        return self._payments[row] if 0 <= row < len(self._payments) else None

    def _pay(self) -> None:
        if register_payment_flow(self._conn, self._user, self._customer_id, self):
            self.refresh()

    def _reprint(self) -> None:
        p = self._selected_payment()
        if p is None:
            QMessageBox.information(self, "Abono", "Elija un abono de la lista.")
            return
        print_with_fallback(
            self,
            lambda: print_service.print_credit_receipt(self._conn, p.id, reprint=True),
            lambda: print_service.save_credit_receipt_pdf(self._conn, p.id),
        )

    def _void(self) -> None:
        p = self._selected_payment()
        if p is None or p.voided:
            return
        reason, ok = QInputDialog.getText(
            self, "Anular abono", f"Anular el abono {p.doc_number} por {format_usd(p.amount_usd)}.\n\nMotivo:"
        )
        if ok:
            run_action(
                self, lambda: credit_service.void_payment(self._conn, self._user, p.id, reason), "No se pudo anular"
            )
            self.refresh()


# ------------------------------------------------------------------ cliente (RF-70)


class CustomerCreditDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, customer_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._customer_id = customer_id
        c = customer_service.get(conn, customer_id)
        default_days = settings_service.load(conn).default_credit_days
        self.setWindowTitle(f"Cliente — {c.name}")
        self.name = QLineEdit(c.name)
        self.phone = QLineEdit(c.phone)
        self.enabled = QCheckBox("Puede comprar a fiado")
        self.enabled.setChecked(c.credit_enabled)
        self.limit = QLineEdit(decimal_field_text(c.credit_limit_usd, 2) if c.credit_limit_usd is not None else "")
        self.limit.setPlaceholderText("En blanco = sin límite")
        self.days = QLineEdit(str(c.credit_days) if c.credit_days else "")
        self.days.setPlaceholderText(f"En blanco = {default_days} días (configuración)")
        form = QFormLayout(self)
        form.addRow("Cédula / RIF:", QLabel(customer_service.format_id_doc(c.id_doc)))
        form.addRow("Nombre:", self.name)
        form.addRow("Teléfono:", self.phone)
        form.addRow("", self.enabled)
        form.addRow("Límite de fiado USD:", self.limit)
        form.addRow("Plazo (días):", self.days)
        save = _button("Guardar")
        cancel = _button("Cancelar")
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(save)
        form.addRow(row)

    def _save(self) -> None:
        def action() -> bool:
            limit: Decimal | None = read_decimal(self.limit, "Límite") if self.limit.text().strip() else None
            days_text = self.days.text().strip()
            if days_text and not days_text.isdigit():
                raise ValueError("El plazo debe ser un número entero de días.")
            days = int(days_text) if days_text else None
            credit_service.update_customer_info(
                self._conn, self._user, self._customer_id, self.name.text(), self.phone.text()
            )
            credit_service.set_customer_credit(
                self._conn, self._user, self._customer_id, self.enabled.isChecked(), limit, days
            )
            return True

        if run_action(self, action):
            self.accept()


# ------------------------------------------------------------------ ventana


class CreditWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Fiado")
        self.resize(1100, 640)
        self.tabs = QTabWidget()

        # deudores
        debtors_tab = QWidget()
        self.debtors = _table(
            ["Cliente", "Cédula/RIF", "Teléfono", "Debe USD", "Vencido USD", "Vence la más vieja", "Notas"]
        )
        self.debtors.doubleClicked.connect(lambda _: self._statement(self._debtor_id()))
        self.total = QLabel()
        self.total.setStyleSheet("font-size: 14pt; font-weight: bold;")
        d_statement = _button("Estado de cuenta (Enter)")
        d_pay = _button("Registrar abono")
        d_statement.clicked.connect(lambda: self._statement(self._debtor_id()))
        d_pay.clicked.connect(lambda: self._pay(self._debtor_id()))
        dl = QVBoxLayout(debtors_tab)
        dl.addWidget(self.debtors, 1)
        db = QHBoxLayout()
        db.addWidget(self.total, 1)
        db.addWidget(d_statement)
        db.addWidget(d_pay)
        dl.addLayout(db)
        self.tabs.addTab(debtors_tab, "Deudores")

        # clientes
        customers_tab = QWidget()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre o cédula/RIF")
        self.search.textChanged.connect(lambda _: self._refresh_customers())
        self.customers = _table(["Cliente", "Cédula/RIF", "Teléfono", "Fiado", "Límite USD", "Plazo", "Debe USD"])
        self.customers.doubleClicked.connect(lambda _: self._statement(self._customer_id()))
        new = _button("Nuevo cliente")
        edit = _button("Configurar fiado…")
        edit.setVisible(user.is_owner)
        c_statement = _button("Estado de cuenta")
        c_pay = _button("Registrar abono")
        new.clicked.connect(self._new_customer)
        edit.clicked.connect(self._edit_customer)
        c_statement.clicked.connect(lambda: self._statement(self._customer_id()))
        c_pay.clicked.connect(lambda: self._pay(self._customer_id()))
        cl = QVBoxLayout(customers_tab)
        cl.addWidget(self.search)
        cl.addWidget(self.customers, 1)
        cb = QHBoxLayout()
        for b in (new, edit):
            cb.addWidget(b)
        cb.addStretch(1)
        for b in (c_statement, c_pay):
            cb.addWidget(b)
        cl.addLayout(cb)
        self.tabs.addTab(customers_tab, "Clientes")

        close = _button("Cerrar")
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self.refresh()

    def refresh(self) -> None:
        self._refresh_debtors()
        self._refresh_customers()

    def _refresh_debtors(self) -> None:
        from datetime import date

        today = date.today()
        self._debtor_rows = credit_service.debtors(self._conn, today)
        self.debtors.setRowCount(len(self._debtor_rows))
        overdue_total = ZERO
        for row, d in enumerate(self._debtor_rows):
            overdue_total += d.overdue_usd
            _fill(
                self.debtors,
                row,
                [
                    (d.name, False),
                    (customer_service.format_id_doc(d.id_doc), False),
                    (d.phone, False),
                    (format_usd(d.balance_usd), True),
                    (format_usd(d.overdue_usd) if d.overdue_usd else "", True),
                    (format_date(d.oldest_due), False),
                    (str(d.open_count), True),
                ],
                OVERDUE if d.overdue_usd else None,
            )
        self.debtors.resizeColumnsToContents()
        self.debtors.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        total = credit_service.total_receivable(self._conn)
        extra = f" · vencido {format_usd(overdue_total)}" if overdue_total else ""
        self.total.setText(f"Total por cobrar: {format_usd(total)}{extra}")

    def _refresh_customers(self) -> None:
        self._customer_rows = credit_service.list_customers(self._conn, self.search.text())
        self.customers.setRowCount(len(self._customer_rows))
        for row, c in enumerate(self._customer_rows):
            balance = credit_service.customer_balance(self._conn, c.id)
            _fill(
                self.customers,
                row,
                [
                    (c.name, False),
                    (customer_service.format_id_doc(c.id_doc), False),
                    (c.phone, False),
                    ("Sí" if c.credit_enabled else "No", False),
                    (format_usd(c.credit_limit_usd) if c.credit_limit_usd is not None else "", True),
                    (f"{c.credit_days} días" if c.credit_days else "", True),
                    (format_usd(balance) if balance else "", True),
                ],
            )
        self.customers.resizeColumnsToContents()
        self.customers.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _debtor_id(self) -> int | None:
        row = self.debtors.currentRow()
        return self._debtor_rows[row].customer_id if 0 <= row < len(self._debtor_rows) else None

    def _customer_id(self) -> int | None:
        row = self.customers.currentRow()
        return self._customer_rows[row].id if 0 <= row < len(self._customer_rows) else None

    def _statement(self, customer_id: int | None) -> None:
        if customer_id is not None:
            StatementDialog(self._conn, self._user, customer_id, self).exec()
            self.refresh()

    def _pay(self, customer_id: int | None) -> None:
        if customer_id is not None and register_payment_flow(self._conn, self._user, customer_id, self):
            self.refresh()

    def _new_customer(self) -> None:
        from repuestos.ui.sale_window import CustomerDialog

        d = CustomerDialog(self._conn, self._user, self)
        d.exec()
        self.refresh()

    def _edit_customer(self) -> None:
        cid = self._customer_id()
        if (
            cid is not None
            and CustomerCreditDialog(self._conn, self._user, cid, self).exec() == QDialog.DialogCode.Accepted
        ):
            self.refresh()
