"""Reportes (RF-80 a RF-84) con vista previa en pantalla antes de imprimir, y bitácora (RF-05)."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QRect, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.users import User
from repuestos.formatting import format_date
from repuestos.printing.reports import MONTHS
from repuestos.services import audit_service, print_service, user_service
from repuestos.ui.common import run_action


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pydate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def _date_edit(d: date) -> QDateEdit:
    e = QDateEdit(_qdate(d))
    e.setCalendarPopup(True)
    e.setDisplayFormat("dd/MM/yyyy")
    return e


# ------------------------------------------------------------------ vista previa


class PdfPreviewDialog(QDialog):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Vista previa — {path.name}")
        self.resize(900, 900)
        self.document = QPdfDocument(self)
        self.document.load(str(path))
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        print_button = QPushButton("Imprimir…")
        save = QPushButton("Guardar como…")
        open_viewer = QPushButton("Abrir en el visor de PDF")
        close = QPushButton("Cerrar")
        for b in (print_button, save, open_viewer, close):
            b.setAutoDefault(False)
        print_button.clicked.connect(self._print)
        save.clicked.connect(self._save_as)
        open_viewer.clicked.connect(lambda: os.startfile(self.path))  # type: ignore[attr-defined]
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(QLabel(f"{self.document.pageCount()} página(s)"))
        buttons.addStretch(1)
        for b in (print_button, save, open_viewer, close):
            buttons.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addLayout(buttons)

    def _print(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        try:
            for i in range(self.document.pageCount()):
                if i:
                    printer.newPage()
                area = painter.viewport()
                page = self.document.pagePointSize(i)
                scale = min(area.width() / page.width(), area.height() / page.height())
                size = QSize(int(page.width() * scale), int(page.height() * scale))
                image = self.document.render(i, size)
                painter.drawImage(QRect(area.x(), area.y(), size.width(), size.height()), image)
        finally:
            painter.end()

    def _save_as(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self, "Guardar reporte", self.path.name, "PDF (*.pdf)")
        if name:
            shutil.copyfile(self.path, name)


def show_pdf(parent: QWidget | None, make: Callable[[], Path]) -> Path | None:
    path = run_action(parent, make, "No se pudo generar el reporte")
    if path is not None:
        PdfPreviewDialog(path, parent).exec()
    return path


# ------------------------------------------------------------------ reportes


class ReportsWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Reportes")
        self.setMinimumWidth(680)
        today = date.today()
        grid = QGridLayout()
        row = 0

        def add(label: str, controls: list[QWidget], action: Callable[[], Path]) -> None:
            nonlocal row
            button = QPushButton("Ver")
            button.setAutoDefault(False)
            button.clicked.connect(lambda: show_pdf(self, action))
            title = QLabel(f"<b>{label}</b>")
            grid.addWidget(title, row, 0)
            box = QWidget()
            hb = QHBoxLayout(box)
            hb.setContentsMargins(0, 0, 0, 0)
            for c in controls:
                hb.addWidget(c)
            hb.addStretch(1)
            grid.addWidget(box, row, 1)
            grid.addWidget(button, row, 2)
            row += 1

        self.day = _date_edit(today)
        add(
            "Ventas del día" if user.is_owner else "Mis ventas del día",
            [self.day],
            lambda: print_service.daily_sales_pdf(conn, user, _pydate(self.day.date())),
        )
        if user.is_owner:
            self.start = _date_edit(today.replace(day=1))
            self.end = _date_edit(today)
            add(
                "Monto vendido por período",
                [QLabel("Desde"), self.start, QLabel("hasta"), self.end],
                lambda: print_service.period_sales_pdf(
                    conn, user, _pydate(self.start.date()), _pydate(self.end.date())
                ),
            )
            self.month = QComboBox()
            for i, name in enumerate(MONTHS, 1):
                self.month.addItem(name.capitalize(), i)
            self.month.setCurrentIndex(today.month - 1)
            self.year = QSpinBox()
            self.year.setRange(2024, 2100)
            self.year.setValue(today.year)
            add(
                "Resumen del mes",
                [self.month, self.year],
                lambda: print_service.month_summary_pdf(conn, user, self.year.value(), self.month.currentData()),
            )
            add("Inventario valorizado", [], lambda: print_service.valued_inventory_pdf(conn, user))
            add("Para pedir", [], lambda: print_service.to_order_pdf(conn, user))

        close = QPushButton("Cerrar")
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(QLabel("Los reportes se abren en una vista previa; desde ahí se imprimen o se guardan."))
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)


# ------------------------------------------------------------------ bitácora (RF-05)


def _details(text: str | None) -> str:
    if not text:
        return ""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    return " · ".join(f"{k}: {v}" for k, v in data.items()) if isinstance(data, dict) else str(data)


class AuditWindow(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle("Bitácora")
        self.resize(1150, 640)
        today = date.today()
        self.date_from = _date_edit(today.replace(day=1))
        self.date_to = _date_edit(today)
        self.who = QComboBox()
        self.who.addItem("Todos los usuarios", None)
        for u in user_service.list_users(conn, user):
            self.who.addItem(u.full_name, u.id)
        self.action = QComboBox()
        self.action.addItem("Todas las acciones", None)
        for a in sorted(audit_service.known_actions(conn), key=audit_service.action_label):
            self.action.addItem(audit_service.action_label(a), a)
        for w in (self.date_from, self.date_to):
            w.dateChanged.connect(lambda _: self.refresh())
        for c in (self.who, self.action):
            c.currentIndexChanged.connect(lambda _: self.refresh())
        filters = QHBoxLayout()
        for w in (QLabel("Desde"), self.date_from, QLabel("hasta"), self.date_to, self.who, self.action):
            filters.addWidget(w)
        filters.addStretch(1)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Fecha", "Usuario", "Autorizó", "Acción", "Detalle"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.count = QLabel()
        close = QPushButton("Cerrar")
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(self.count, 1)
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self) -> None:
        entries = audit_service.list_entries(
            self._conn,
            self._user,
            _pydate(self.date_from.date()),
            _pydate(self.date_to.date()),
            self.who.currentData(),
            self.action.currentData(),
        )
        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            values = [
                f"{format_date(e.created_at)} {e.created_at[11:16]}",
                e.user_name or "—",
                e.authorized_by_name or "",
                audit_service.action_label(e.action),
                _details(e.details_json),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.count.setText(f"{len(entries)} registros (se muestran hasta 2.000)")
