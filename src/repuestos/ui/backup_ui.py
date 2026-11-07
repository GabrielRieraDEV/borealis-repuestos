"""Respaldo en segundo plano (RF-90) y diálogo de respaldo y restauración (RF-91)."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repuestos.config import get_paths
from repuestos.domain.users import User
from repuestos.services import backup_service
from repuestos.ui.common import run_action

log = logging.getLogger(__name__)


class _Worker(QObject):
    done = Signal(object)  # BackupResult
    failed = Signal(str)

    def __init__(self, with_pdfs: bool) -> None:
        super().__init__()
        self._with_pdfs = with_pdfs

    def run(self) -> None:
        try:
            self.done.emit(backup_service.run_backup(get_paths(), with_pdfs=self._with_pdfs))
        except Exception as exc:  # nunca tumba el programa; queda en el log y en la barra de estado
            log.exception("Falló el respaldo")
            self.failed.emit(str(exc))


class BackupManager(QObject):
    """Corre el respaldo en un hilo aparte (tiene su propia conexión): la pantalla no se congela."""

    finished = Signal(bool, str)  # ok, mensaje

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._pending_pdfs: bool | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, with_pdfs: bool = False) -> None:
        if self._thread is not None:
            # ya hay uno en curso: se encola uno más al terminar (p. ej. cierre de caja durante el de arranque)
            self._pending_pdfs = bool(self._pending_pdfs) or with_pdfs
            return
        self._thread = QThread()
        self._worker = _Worker(with_pdfs)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None
        if self._pending_pdfs is not None:
            pdfs, self._pending_pdfs = self._pending_pdfs, None
            self.start(pdfs)

    def _on_done(self, result: backup_service.BackupResult) -> None:
        message = f"Respaldo listo: {result.local.name}"
        if result.cloud_error:
            message += f". {result.cloud_error}"
        self._cleanup()
        self.finished.emit(result.cloud_error is None, message)

    def _on_failed(self, message: str) -> None:
        self._cleanup()
        self.finished.emit(False, message)

    def wait(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(30000)


def _item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def describe(path: Path) -> str:
    stem = path.stem  # romero_20261107_1830[_antes_de_restaurar]
    parts = stem.split("_")
    when = f"{parts[1][6:8]}/{parts[1][4:6]}/{parts[1][:4]} {parts[2][:2]}:{parts[2][2:4]}"
    return when + ("  (antes de restaurar)" if stem.endswith("antes_de_restaurar") else "")


class BackupDialog(QDialog):
    """Dueña: ver respaldos, respaldar ahora, restaurar (doble confirmación) y abrir la carpeta."""

    def __init__(self, conn: sqlite3.Connection, user: User, manager: BackupManager, parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._manager = manager
        self.restore_path: Path | None = None  # la ventana principal reinicia el programa con esto
        self.setWindowTitle("Respaldo")
        self.resize(640, 520)
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Respaldo", "Tamaño"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        now = QPushButton("Respaldar ahora")
        restore = QPushButton("Restaurar el elegido…")
        other = QPushButton("Restaurar desde otro archivo…")
        folder = QPushButton("Abrir carpeta")
        close = QPushButton("Cerrar")
        for b in (now, restore, other, folder, close):
            b.setAutoDefault(False)
        now.clicked.connect(self._backup_now)
        restore.clicked.connect(self._restore_selected)
        other.clicked.connect(self._restore_other)
        folder.clicked.connect(lambda: os.startfile(get_paths().backup_dir))  # type: ignore[attr-defined]
        close.clicked.connect(self.accept)
        manager.finished.connect(self._finished)
        buttons = QHBoxLayout()
        for b in (now, restore, other, folder):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.state)
        layout.addWidget(QLabel(f"Respaldos en {get_paths().backup_dir} (se guardan los últimos 30):"))
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self.refresh()

    def done(self, result: int) -> None:
        self._manager.finished.disconnect(self._finished)
        super().done(result)

    def refresh(self) -> None:
        st = backup_service.status(self._conn)
        local = st.last_local.strftime("%d/%m/%Y %H:%M") if st.last_local else "nunca"
        cloud = st.last_cloud.strftime("%d/%m/%Y %H:%M") if st.last_cloud else "nunca"
        cloud_line = f"En la nube: {cloud}" if st.cloud_configured else "Carpeta de la nube: <b>sin configurar</b>"
        warn = " <span style='color:#b00020'>(más de 48 horas)</span>" if st.cloud_configured and st.cloud_stale else ""
        self.state.setText(f"Último respaldo local: <b>{local}</b><br>{cloud_line}{warn}")
        self.backups = backup_service.list_backups(get_paths())
        self.table.setRowCount(len(self.backups))
        for row, path in enumerate(self.backups):
            self.table.setItem(row, 0, _item(describe(path)))
            self.table.setItem(row, 1, _item(f"{path.stat().st_size / 1_048_576:.1f} MB".replace(".", ",")))

    def _backup_now(self) -> None:
        self.state.setText("Respaldando…")
        self._manager.start(with_pdfs=True)

    def _finished(self, ok: bool, message: str) -> None:
        self.refresh()
        if not ok:
            QMessageBox.warning(self, "Respaldo", message)

    def _confirm_and_restore(self, path: Path) -> None:
        if run_action(self, lambda: backup_service.check_can_restore(self._user, path) or True, "Restaurar") is None:
            return
        if (
            QMessageBox.question(
                self,
                "Restaurar respaldo",
                f"Se reemplazarán TODOS los datos actuales por los del respaldo {describe(path)}.\n"
                "Lo que se hizo después de ese respaldo dejará de verse (antes se guarda una copia).\n\n¿Continuar?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        text, ok = QInputDialog.getText(self, "Confirmación", "Para confirmar escriba RESTAURAR:")
        if not ok or text.strip().upper() != "RESTAURAR":
            QMessageBox.information(self, "Restaurar", "No se restauró nada.")
            return
        self.restore_path = path
        self.accept()

    def _restore_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.backups):
            self._confirm_and_restore(self.backups[row])

    def _restore_other(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Elegir respaldo", str(get_paths().backup_dir), "Respaldos (*.db)")
        if name:
            self._confirm_and_restore(Path(name))
