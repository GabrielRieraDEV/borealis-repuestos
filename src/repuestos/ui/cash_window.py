"""Caja (RF-60 a RF-63): apertura, entradas y salidas, cierre ciego e historial (dueña)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
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
    QPlainTextEdit,
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
from repuestos.formatting import format_date, format_usd, format_ves
from repuestos.services import cash_service, print_service
from repuestos.ui.common import read_decimal, run_action
from repuestos.ui.print_helpers import print_with_fallback


def _when(ts: str | None) -> str:
    return f"{format_date(ts)} {ts[11:16]}" if ts else ""


def _cell(text: str, right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class CloseDialog(QDialog):
    """Cierre ciego: se escribe lo contado, sin ver lo esperado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cerrar caja")
        self.counted_usd = QLineEdit()
        self.counted_ves = QLineEdit()
        self.notes = QLineEdit()
        form = QFormLayout(self)
        form.addRow(QLabel("Cuente el efectivo que hay en la caja y escríbalo:"))
        form.addRow("Efectivo USD contado:", self.counted_usd)
        form.addRow("Efectivo Bs contado:", self.counted_ves)
        form.addRow("Notas (opcional):", self.notes)
        buttons = QHBoxLayout()
        ok = QPushButton("Cerrar caja")
        cancel = QPushButton("Cancelar")
        ok.setAutoDefault(False)
        cancel.setAutoDefault(False)
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        form.addRow(buttons)
        self.counted_usd.returnPressed.connect(self.counted_ves.setFocus)
        self.counted_ves.returnPressed.connect(self.notes.setFocus)
        self.notes.returnPressed.connect(self._accept)
        self.values = None

    def _accept(self) -> None:
        def read():
            return read_decimal(self.counted_usd, "Efectivo USD"), read_decimal(self.counted_ves, "Efectivo Bs")

        values = run_action(self, read, "Revise los montos")
        if values is not None:
            self.values = values
            self.accept()


class CashWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Caja")
        self.resize(1000, 640)
        self.tabs = QTabWidget()
        self.current_tab = QWidget()
        self.tabs.addTab(self.current_tab, "Caja actual")
        if user.is_owner:
            self.history = QTableWidget(0, 9)
            self.history.setHorizontalHeaderLabels(
                [
                    "Nro",
                    "Abrió",
                    "Cerró",
                    "Por",
                    "Esperado USD",
                    "Contado USD",
                    "Diferencia USD",
                    "Esperado Bs",
                    "Diferencia Bs",
                ]
            )
            self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.history.verticalHeader().setVisible(False)
            self.history.doubleClicked.connect(lambda _: self._history_detail())
            history_tab = QWidget()
            hl = QVBoxLayout(history_tab)
            hl.addWidget(self.history, 1)
            detail = QPushButton("Ver / reimprimir cierre")
            detail.clicked.connect(self._history_detail)
            hl.addWidget(detail, 0, Qt.AlignmentFlag.AlignRight)
            self.tabs.addTab(history_tab, "Historial de cierres")
        close = QPushButton("Cerrar ventana")
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self._build_current()
        self.refresh()

    # ------------------------------------------------------------------ caja actual

    def _build_current(self) -> None:
        layout = QVBoxLayout(self.current_tab)
        self.state = QLabel()
        self.state.setStyleSheet("font-size: 14pt;")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)

        # apertura
        self.open_box = QWidget()
        of = QFormLayout(self.open_box)
        self.opening_usd = QLineEdit("0")
        self.opening_ves = QLineEdit("0")
        open_button = QPushButton("Abrir caja")
        open_button.setAutoDefault(False)
        open_button.clicked.connect(self._open)
        self.opening_usd.returnPressed.connect(self.opening_ves.setFocus)
        self.opening_ves.returnPressed.connect(self._open)
        of.addRow("Efectivo inicial USD:", self.opening_usd)
        of.addRow("Efectivo inicial Bs:", self.opening_ves)
        of.addRow(open_button)
        layout.addWidget(self.open_box)

        # caja abierta: entradas/salidas y cierre
        self.open_panel = QWidget()
        pl = QVBoxLayout(self.open_panel)
        self.expected = QLabel()
        self.expected.setWordWrap(True)
        pl.addWidget(self.expected)
        row = QHBoxLayout()
        self.direction = QComboBox()
        self.direction.addItem("Salida de efectivo", "OUT")
        self.direction.addItem("Entrada de efectivo", "IN")
        self.currency = QComboBox()
        self.currency.addItem("Bs", "VES")
        self.currency.addItem("USD", "USD")
        self.mv_amount = QLineEdit()
        self.mv_amount.setPlaceholderText("Monto")
        self.mv_reason = QLineEdit()
        self.mv_reason.setPlaceholderText("Motivo (obligatorio)")
        mv_button = QPushButton("Registrar")
        mv_button.setAutoDefault(False)
        mv_button.clicked.connect(self._movement)
        self.mv_reason.returnPressed.connect(self._movement)
        for w in (self.direction, self.currency, self.mv_amount):
            row.addWidget(w)
        row.addWidget(self.mv_reason, 1)
        row.addWidget(mv_button)
        pl.addLayout(row)
        self.movements = QTableWidget(0, 5)
        self.movements.setHorizontalHeaderLabels(["Hora", "Tipo", "Monto", "Motivo", "Usuario"])
        self.movements.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.movements.verticalHeader().setVisible(False)
        self.movements.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        pl.addWidget(self.movements, 1)
        close_button = QPushButton("Cerrar caja…")
        close_button.setStyleSheet("font-size: 13pt; padding: 6px 18px;")
        close_button.setAutoDefault(False)
        close_button.clicked.connect(self._close)
        pl.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.open_panel, 1)

    def refresh(self) -> None:
        session = cash_service.current_session(self._conn)
        self.open_box.setVisible(session is None)
        self.open_panel.setVisible(session is not None)
        if session is None:
            self.state.setText("La caja está <b>cerrada</b>. Para vender, ábrala con el efectivo que hay ahora.")
            self.opening_usd.setFocus()
        else:
            self.state.setText(
                f"Caja Nro. {session.id} <b>abierta</b> por {session.opened_by_name} el {_when(session.opened_at)}."
                f" Apertura: {format_usd(session.opening_usd)} y {format_ves(session.opening_ves)}."
            )
            if self._user.is_owner:
                s = cash_service.session_summary(self._conn, self._user, session.id)
                non_cash = " · ".join(
                    f"{METHOD_LABELS[n.method]}: "
                    f"{format_usd(n.total) if n.method is PaymentMethod.USDT else format_ves(n.total)} ({n.count})"
                    for n in s.non_cash
                )
                expected_usd = format_usd(s.expected_usd or ZERO)
                expected_ves = format_ves(s.expected_ves or ZERO)
                self.expected.setText(
                    f"Esperado ahora: <b>{expected_usd}</b> y <b>{expected_ves}</b>"
                    f" · {s.sales_count} venta{'s' if s.sales_count != 1 else ''} por {format_ves(s.sales_total_ves)}"
                    f"<br>{non_cash}"
                )
            else:
                self.expected.setText("")
            moves = cash_service.blind_summary(self._conn, session.id).movements
            self.movements.setRowCount(len(moves))
            for r, m in enumerate(moves):
                amount = format_usd(m.amount) if m.currency == "USD" else format_ves(m.amount)
                for c, (text, right) in enumerate(
                    [
                        (m.created_at[11:16], False),
                        ("Entrada" if m.direction == "IN" else "Salida", False),
                        (amount, True),
                        (m.reason, False),
                        (m.user_name, False),
                    ]
                ):
                    self.movements.setItem(r, c, _cell(text, right))
            self.movements.resizeColumnsToContents()
            self.movements.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        if self._user.is_owner:
            self._refresh_history()

    def _open(self) -> None:
        def action():
            return cash_service.open_session(
                self._conn,
                self._user,
                read_decimal(self.opening_usd, "Efectivo inicial USD"),
                read_decimal(self.opening_ves, "Efectivo inicial Bs"),
            )

        if run_action(self, action, "No se pudo abrir la caja") is not None:
            self.refresh()

    def _movement(self) -> None:
        def action():
            return cash_service.add_movement(
                self._conn,
                self._user,
                self.direction.currentData(),
                self.currency.currentData(),
                read_decimal(self.mv_amount, "Monto"),
                self.mv_reason.text(),
            )

        if run_action(self, action) is not None:
            self.mv_amount.clear()
            self.mv_reason.clear()
            self.refresh()

    def _close(self) -> None:
        d = CloseDialog(self)
        if d.exec() != QDialog.DialogCode.Accepted or d.values is None:
            return
        usd, ves = d.values
        result = run_action(
            self,
            lambda: cash_service.close_session(self._conn, self._user, usd, ves, d.notes.text()),
            "No se pudo cerrar",
        )
        if result is None:
            return
        if self._user.is_owner:
            s = cash_service.session_summary(self._conn, self._user, result.session_id)
            QMessageBox.information(
                self,
                "Cierre registrado",
                f"Esperado: {format_usd(s.expected_usd or ZERO)} y {format_ves(s.expected_ves or ZERO)}\n"
                f"Contado: {format_usd(usd)} y {format_ves(ves)}\n"
                f"Diferencia USD: {format_usd(s.difference_usd or ZERO)}\n"
                f"Diferencia Bs: {format_ves(s.difference_ves or ZERO)}",
            )
        else:
            QMessageBox.information(self, "Caja", "Cierre registrado.")
        print_with_fallback(
            self,
            lambda: print_service.print_close(self._conn, self._user, result.session_id),
            lambda: print_service.save_close_pdf(self._conn, self._user, result.session_id),
        )
        self.refresh()

    # ------------------------------------------------------------------ historial (dueña)

    def _refresh_history(self) -> None:
        self.sessions = cash_service.history(self._conn, self._user)
        self.history.setRowCount(len(self.sessions))
        for r, s in enumerate(self.sessions):
            diff_usd = (
                s.counted_usd - s.expected_usd if s.counted_usd is not None and s.expected_usd is not None else None
            )
            diff_ves = (
                s.counted_ves - s.expected_ves if s.counted_ves is not None and s.expected_ves is not None else None
            )
            values = [
                (str(s.id), False),
                (_when(s.opened_at), False),
                (_when(s.closed_at) or "abierta", False),
                (s.closed_by_name or s.opened_by_name, False),
                (format_usd(s.expected_usd) if s.expected_usd is not None else "", True),
                (format_usd(s.counted_usd) if s.counted_usd is not None else "", True),
                (format_usd(diff_usd) if diff_usd is not None else "", True),
                (format_ves(s.expected_ves) if s.expected_ves is not None else "", True),
                (format_ves(diff_ves) if diff_ves is not None else "", True),
            ]
            for c, (text, right) in enumerate(values):
                item = _cell(text, right)
                if c in (6, 8) and text and (diff_usd if c == 6 else diff_ves):
                    item.setForeground(Qt.GlobalColor.red)
                self.history.setItem(r, c, item)
        self.history.resizeColumnsToContents()

    def _history_detail(self) -> None:
        row = self.history.currentRow()
        if not 0 <= row < len(self.sessions):
            return
        session_id = self.sessions[row].id
        d = QDialog(self)
        d.setWindowTitle(f"Cierre de caja Nro. {session_id}")
        d.resize(520, 640)
        text = QPlainTextEdit("\n".join(print_service.close_lines(self._conn, self._user, session_id)))
        text.setReadOnly(True)
        text.setStyleSheet("font-family: Consolas, 'Courier New'; font-size: 10pt;")
        reprint = QPushButton("Reimprimir")
        reprint.clicked.connect(
            lambda: print_with_fallback(
                d,
                lambda: print_service.print_close(self._conn, self._user, session_id),
                lambda: print_service.save_close_pdf(self._conn, self._user, session_id),
            )
        )
        lay = QVBoxLayout(d)
        lay.addWidget(text, 1)
        lay.addWidget(reprint, 0, Qt.AlignmentFlag.AlignRight)
        d.exec()
