"""Arranque: carpetas, log, base de datos y migraciones, primer arranque, login y ventana principal."""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from repuestos.config import APP_NAME, get_paths
from repuestos.db import migrate
from repuestos.db.connection import connect
from repuestos.db.repositories import settings as settings_repo
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

    from repuestos.services import auth_service, setup_service
    from repuestos.ui.login import LoginDialog
    from repuestos.ui.main_window import MainWindow
    from repuestos.ui.setup_wizard import SetupWizard

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    font = app.font()
    font.setPointSize(11)
    app.setFont(font)
    _install_excepthook()

    if setup_service.needs_setup(conn):
        wizard = SetupWizard(conn)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return 0

    business_name = settings_repo.get(conn, "business_name")
    login = LoginDialog(conn, business_name)
    if login.exec() != QDialog.DialogCode.Accepted or login.user is None:
        return 0
    user = login.user

    window = MainWindow(user, business_name)
    window.show()
    code = app.exec()
    auth_service.logout(conn, user)
    conn.close()
    log.info("Cierre normal")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
