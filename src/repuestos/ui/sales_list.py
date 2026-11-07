"""Ventas del día (RF-56): detalle, reimpresión y anulación (RF-53). El vendedor ve solo las suyas."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.money import ZERO
from repuestos.domain.users import User
from repuestos.formatting import format_usd, format_ves
from repuestos.services import print_service, sale_service
from repuestos.ui.authorize_dialog import ask_owner_authorization
from repuestos.ui.common import run_action
from repuestos.ui.print_helpers import print_with_fallback


def _cell(text: str, right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class SalesListWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Ventas del día")
        self.resize(1050, 600)
        today = date.today()
        self.day = QDateEdit(QDate(today.year, today.month, today.day))
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat("dd/MM/yyyy")
        self.day.dateChanged.connect(lambda _: self.refresh())
        top = QHBoxLayout()
        top.addWidget(QLabel("Día:"))
        top.addWidget(self.day)
        top.addStretch(1)
        if not user.is_owner:
            top.addWidget(QLabel("Se muestran solo sus ventas."))

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Nota", "Hora", "Cliente", "Vendedor", "Total Bs", "Ref. USD", "Estado"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(lambda _: self._detail())
        self.summary = QLabel()

        detail = QPushButton("Ver detalle")
        reprint = QPushButton("Reimprimir")
        void = QPushButton("Anular venta…")
        close = QPushButton("Cerrar")
        for b in (detail, reprint, void, close):
            b.setAutoDefault(False)
        detail.clicked.connect(self._detail)
        reprint.clicked.connect(self._reprint)
        void.clicked.connect(self._void)
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        for b in (detail, reprint, void, close):
            bottom.addWidget(b)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        self.sales: list = []
        self.refresh()

    def refresh(self) -> None:
        q = self.day.date()
        self.sales = sale_service.list_sales(self._conn, self._user, date(q.year(), q.month(), q.day()))
        self.table.setRowCount(len(self.sales))
        total = ZERO
        for r, s in enumerate(self.sales):
            if not s.voided:
                total += s.total_ves
            values = [
                (s.doc_number, False),
                (s.created_at[11:16], False),
                (s.customer_name, False),
                (s.user_name, False),
                (format_ves(s.total_ves), True),
                (format_usd(s.total_usd), True),
                ("ANULADA" if s.voided else "", False),
            ]
            for c, (text, right) in enumerate(values):
                item = _cell(text, right)
                if s.voided:
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        n = sum(1 for s in self.sales if not s.voided)
        self.summary.setText(f"{n} venta{'s' if n != 1 else ''} · {format_ves(total)} (sin anuladas)")

    def _selected(self):
        row = self.table.currentRow()
        return self.sales[row] if 0 <= row < len(self.sales) else None

    def _detail(self) -> None:
        s = self._selected()
        if s is None:
            return
        d = QDialog(self)
        d.setWindowTitle(f"Nota {s.doc_number}")
        d.resize(520, 700)
        text = QPlainTextEdit("\n".join(print_service.sale_lines(self._conn, self._user, s.id, reprint=True)))
        text.setReadOnly(True)
        text.setStyleSheet("font-family: Consolas, 'Courier New'; font-size: 10pt;")
        lay = QVBoxLayout(d)
        lay.addWidget(text)
        d.exec()

    def _reprint(self) -> None:
        s = self._selected()
        if s is None:
            return
        print_with_fallback(
            self,
            lambda: print_service.print_sale(self._conn, self._user, s.id, reprint=True),
            lambda: print_service.save_sale_pdf(self._conn, self._user, s.id),
        )

    def _void(self) -> None:
        s = self._selected()
        if s is None or s.voided:
            return
        reason, ok = QInputDialog.getText(
            self,
            "Anular venta",
            f"Anular la nota {s.doc_number} por {format_ves(s.total_ves)}.\n"
            "Las existencias vuelven al inventario y los pagos se anulan.\n\nMotivo:",
        )
        if not ok or not reason.strip():
            return
        authorized_by = None
        if not self._user.is_owner:
            authorized_by = ask_owner_authorization(self._conn, self._user, f"anular la nota {s.doc_number}", self)
            if authorized_by is None:
                return
        run_action(
            self,
            lambda: sale_service.void_sale(self._conn, self._user, s.id, reason, authorized_by),
            "No se pudo anular",
        )
        self.refresh()
