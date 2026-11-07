"""Tasa BCV en la interfaz: descarga en segundo plano (RF-20), carga manual (RF-21) y diálogo."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.domain.users import User
from repuestos.services import bcv, rate_service
from repuestos.services.rate_service import SOURCE_LABELS
from repuestos.ui.common import read_decimal, run_action
from repuestos.ui.formatting import format_date, format_rate

log = logging.getLogger(__name__)

FETCH_INTERVAL_MS = 2 * 60 * 60 * 1000  # cada 2 horas (RN-01)


class _FetchWorker(QObject):
    done = Signal(object)  # BcvRate
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.done.emit(bcv.fetch_bcv_rate())
        except bcv.BcvError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # nunca debe tumbar el programa
            log.exception("Error inesperado al descargar la tasa")
            self.failed.emit(str(exc))


class BcvFetcher(QObject):
    """Descarga la tasa en un hilo aparte; el guardado ocurre en el hilo principal. Nunca bloquea la UI."""

    updated = Signal()  # se guardó o cambió una tasa
    finished = Signal(bool, str)  # ok, mensaje

    def __init__(self, conn: sqlite3.Connection, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._thread: QThread | None = None
        self._worker: _FetchWorker | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = QThread()
        self._worker = _FetchWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None
        self._worker = None

    def _on_done(self, result: bcv.BcvRate) -> None:
        self._cleanup()
        try:
            changed = rate_service.save_bcv_rate(self._conn, result.rate, result.valid_date)
        except Exception as exc:
            log.exception("No se pudo guardar la tasa del BCV")
            self.finished.emit(False, str(exc))
            return
        log.info("Tasa BCV %s con fecha valor %s (cambió: %s)", result.rate, result.valid_date, changed)
        if changed:
            self.updated.emit()
        self.finished.emit(True, f"BCV: {format_rate(result.rate)} con fecha valor {format_date(result.valid_date)}")

    def _on_failed(self, message: str) -> None:
        self._cleanup()
        self.finished.emit(False, message)

    def shutdown(self) -> None:
        self._cleanup()


class RateDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: User, fetcher: BcvFetcher, parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._fetcher = fetcher
        self.setWindowTitle("Tasa BCV")
        self.resize(560, 480)

        self.current = QLabel()
        self.current.setStyleSheet("font-size: 14pt;")
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.download = QPushButton("Descargar del BCV ahora")
        self.download.clicked.connect(self._download)
        fetcher.finished.connect(self._fetch_finished)
        fetcher.updated.connect(self.refresh)

        self.manual = QLineEdit()
        self.manual.setPlaceholderText("Ej.: 231,0468")
        save_manual = QPushButton("Guardar tasa de hoy")
        save_manual.clicked.connect(self._save_manual)
        manual_row = QHBoxLayout()
        manual_row.addWidget(QLabel("Cargar a mano:"))
        manual_row.addWidget(self.manual, 1)
        manual_row.addWidget(save_manual)
        manual_box = QWidget()
        manual_box.setLayout(manual_row)
        manual_box.setVisible(user.is_owner)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha valor", "Tasa Bs/USD", "Origen", "Registrada"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self.current)
        layout.addWidget(self.download)
        layout.addWidget(self.message)
        layout.addWidget(manual_box)
        layout.addWidget(QLabel("Últimas tasas:"))
        layout.addWidget(self.table, 1)
        layout.addWidget(close)
        self.refresh()

    def done(self, result: int) -> None:
        self._fetcher.finished.disconnect(self._fetch_finished)
        self._fetcher.updated.disconnect(self.refresh)
        super().done(result)

    def refresh(self) -> None:
        r = rate_service.current_rate(self._conn)
        if r is None:
            self.current.setText("Sin tasa vigente: no se puede vender hasta cargarla.")
        else:
            warn = "  ⚠ tiene más de 3 días" if r.stale else ""
            self.current.setText(
                f"Vigente: <b>{format_rate(r.rate)}</b> Bs/USD · fecha valor {format_date(r.valid_date)}"
                f" · {SOURCE_LABELS[r.source]}{warn}"
            )
        rates = rate_service.recent_rates(self._conn)
        self.table.setRowCount(len(rates))
        for row, x in enumerate(rates):
            for col, text in enumerate(
                [format_date(x.valid_date), format_rate(x.rate), SOURCE_LABELS[x.source], format_date(x.fetched_at)]
            ):
                self.table.setItem(row, col, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def _download(self) -> None:
        self.download.setEnabled(False)
        self.message.setText("Descargando…")
        self._fetcher.start()

    def _fetch_finished(self, ok: bool, message: str) -> None:
        self.download.setEnabled(True)
        if ok:
            self.message.setText(message)
        else:
            self.message.setText(
                "No se pudo descargar la tasa del BCV (sin internet o la página no responde). "
                "Puede cargarla a mano." + (f"\nDetalle: {message}" if message else "")
            )
        self.refresh()

    def _save_manual(self) -> None:
        def action() -> bool:
            rate_service.set_manual_rate(self._conn, self._user, read_decimal(self.manual, "Tasa"))
            return True

        if run_action(self, action):
            self.manual.clear()
            self.message.setText("Tasa manual guardada.")
            self.refresh()
