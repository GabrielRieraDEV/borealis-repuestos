"""Arranque: carpetas, log, base de datos y migraciones, verificación de existencias, login y ventana principal."""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from repuestos.config import APP_NAME, get_paths
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
    paths = get_paths()
    paths.ensure()
    setup_logging(paths.log_dir)
    log.info("Arrancando %s; datos en %s", APP_NAME, paths.base)

    conn = connect(paths.db_path)
    migrate.apply_migrations(conn)

    from PySide6.QtWidgets import QApplication, QDialog

    from repuestos.services import auth_service, settings_service, setup_service
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
        if not window.logout_requested:
            break
    conn.close()
    log.info("Cierre normal")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
