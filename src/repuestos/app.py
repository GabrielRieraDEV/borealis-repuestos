"""Arranque: carpetas, log, base de datos y migraciones, verificación de existencias, login y ventana principal."""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from repuestos.config import APP_NAME, TEST_FLAG, enable_test_mode, get_paths, is_test_mode
from repuestos.db import migrate
from repuestos.db.connection import connect
from repuestos.logging_setup import setup_logging

log = logging.getLogger(__name__)


def _install_excepthook() -> None:
    from PySide6.QtWidgets import QMessageBox

    def hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        log.error("Error no controlado:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        QMessageBox.critical(
            None,
            APP_NAME,
            "Ocurrió un error inesperado. La operación no se guardó a medias.\n"
            "Si se repite, avise a Borealis indicando qué estaba haciendo.",
        )

    sys.excepthook = hook


def main() -> int:
    if TEST_FLAG in sys.argv:
        enable_test_mode()
    paths = get_paths()
    paths.ensure()
    setup_logging(paths.log_dir)
    log.info("Arrancando %s%s; datos en %s", APP_NAME, " (MODO DE PRUEBA)" if is_test_mode() else "", paths.base)

    conn = connect(paths.db_path)
    migrate.apply_migrations(conn)

    from PySide6.QtWidgets import QApplication, QDialog

    from repuestos.services import auth_service, backup_service, report_service, settings_service, setup_service
    from repuestos.tools.verify_stock import verify_and_log
    from repuestos.ui.login import LoginDialog
    from repuestos.ui.main_window import MainWindow
    from repuestos.ui.setup_wizard import SetupWizard
    from repuestos.ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app)
    _install_excepthook()

    if setup_service.needs_setup(conn):
        wizard = SetupWizard(conn)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return 0

    apply_theme(app, settings_service.load(conn).large_font)

    # RN-13: foto de la inversión del mes anterior en el primer arranque del mes, antes de cualquier operación
    taken = report_service.ensure_monthly_snapshot(conn)
    if taken:
        log.info("Foto mensual tomada para %s", taken)

    # RF-44: silenciosa si todo cuadra; si no, bitácora y aviso a la dueña
    mismatches = verify_and_log(conn)
    if mismatches:
        log.warning("verify_stock: %d producto(s) con diferencias", len(mismatches))

    code = 0
    while True:
        login = LoginDialog(conn, settings_service.load(conn).business_name)
        if login.exec() != QDialog.DialogCode.Accepted or login.user is None:
            break
        user = login.user
        window = MainWindow(conn, user)
        window.show()
        if mismatches and user.is_owner:
            window.show_stock_mismatch(len(mismatches))
            mismatches = []
        code = app.exec()
        auth_service.logout(conn, user)
        if window.restore_path is not None:
            return _restore_and_restart(conn, paths, user, window.restore_path)
        if not window.logout_requested:
            break
    conn.close()
    # RF-90 / RF-92: respaldo y PDF de la nube al salir (rápido; si falla queda en el log)
    try:
        backup_service.run_backup(paths, with_pdfs=True)
    except Exception:
        log.exception("Falló el respaldo al salir")
    log.info("Cierre normal")
    return code


def _restore_and_restart(conn, paths, user, backup) -> int:
    """RF-91: se cierra la base (modo exclusivo), se restaura y el programa se abre de nuevo."""
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QMessageBox

    from repuestos.services import backup_service

    conn.close()
    try:
        previous = backup_service.restore(paths, user, backup)
    except Exception:
        log.exception("No se pudo restaurar %s", backup)
        QMessageBox.critical(
            None,
            APP_NAME,
            "No se pudo restaurar el respaldo. Si los datos actuales no abren, avise a Borealis: "
            "la copia previa quedó guardada en la carpeta de respaldos.",
        )
        return 1
    QMessageBox.information(
        None,
        APP_NAME,
        f"Respaldo restaurado. La copia de los datos anteriores quedó como {previous.name}.\n"
        "El programa se abrirá de nuevo.",
    )
    args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    QProcess.startDetached(sys.executable, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
