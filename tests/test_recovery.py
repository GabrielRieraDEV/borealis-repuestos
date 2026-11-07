"""Recuperación de la clave de la dueña con su código (y el último recurso de soporte)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from repuestos.db.migrate import applied_versions
from repuestos.domain.passwords import RECOVERY_ALPHABET, generate_recovery_code, normalize_recovery_code
from repuestos.services import auth_service, recovery_service
from tests.conftest import OWNER_PASSWORD
from tests.helpers import make_seller

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _actions(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]


def test_migracion_0002(conn) -> None:
    assert applied_versions(conn) == {1, 2}
    assert not recovery_service.has_code(conn)


def test_formato_del_codigo() -> None:
    code = generate_recovery_code()
    assert len(code) == 14 and code.count("-") == 2
    assert all(c in RECOVERY_ALPHABET for c in code.replace("-", ""))
    assert normalize_recovery_code(" k7qm 3xr9-pw2h ") == "K7QM3XR9PW2H"
    assert len({generate_recovery_code() for _ in range(50)}) == 50


def test_recuperar_con_el_codigo(conn, owner) -> None:
    code = recovery_service.generate_code(conn, owner)
    assert recovery_service.has_code(conn)
    stored = conn.execute("SELECT value FROM settings WHERE key = 'owner_recovery_hash'").fetchone()[0]
    assert code.replace("-", "") not in stored  # se guarda solo el hash
    user, new_code = recovery_service.reset_owner_password(conn, code.lower().replace("-", " "), "nueva456")
    assert user.id == owner.id and new_code != code
    assert auth_service.login(conn, "yoleida", "nueva456").id == owner.id
    with pytest.raises(auth_service.AuthError):
        auth_service.login(conn, "yoleida", OWNER_PASSWORD)
    with pytest.raises(ValueError, match="no es correcto"):  # el código usado ya no sirve
        recovery_service.reset_owner_password(conn, code, "otra789")
    recovery_service.reset_owner_password(conn, new_code, "otra789")  # el nuevo sí
    assert "OWNER_PASSWORD_RECOVERED" in _actions(conn) and "RECOVERY_FAILED" in _actions(conn)


def test_recuperar_quita_el_bloqueo(conn, owner) -> None:
    code = recovery_service.generate_code(conn, owner)
    for _ in range(5):
        with pytest.raises(auth_service.AuthError):
            auth_service.login(conn, "yoleida", "mala")
    recovery_service.reset_owner_password(conn, code, "nueva456")
    assert auth_service.login(conn, "yoleida", "nueva456").id == owner.id


def test_codigo_incorrecto_o_inexistente(conn, owner) -> None:
    with pytest.raises(ValueError, match="no tiene código"):
        recovery_service.reset_owner_password(conn, "AAAA-AAAA-AAAA", "nueva456")
    recovery_service.generate_code(conn, owner)
    with pytest.raises(ValueError, match="no es correcto"):
        recovery_service.reset_owner_password(conn, "AAAA-AAAA-AAAA", "nueva456")
    with pytest.raises(ValueError, match="6"):
        recovery_service.reset_owner_password(conn, "AAAA-AAAA-AAAA", "123")
    assert auth_service.login(conn, "yoleida", OWNER_PASSWORD).id == owner.id


def test_generar_otro_invalida_el_anterior_y_solo_la_duena(conn, owner) -> None:
    old = recovery_service.generate_code(conn, owner)
    new = recovery_service.generate_code(conn, owner)
    with pytest.raises(ValueError):
        recovery_service.reset_owner_password(conn, old, "nueva456")
    recovery_service.reset_owner_password(conn, new, "nueva456")
    with pytest.raises(PermissionError):
        recovery_service.generate_code(conn, make_seller(conn, owner))


def test_herramienta_de_soporte(tmp_path: Path, owner, conn) -> None:
    from repuestos.tools.reset_owner import reset

    db = tmp_path / "test.db"
    code = reset(db, "soporte1")
    assert auth_service.login(conn, "yoleida", "soporte1").id == owner.id
    recovery_service.reset_owner_password(conn, code, "nueva456")
    assert "OWNER_PASSWORD_RESET_SUPPORT" in _actions(conn)


# ------------------------------------------------------------------ interfaz


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_dialogo_del_codigo_exige_anotarlo(app) -> None:
    from repuestos.ui.recovery_ui import RecoveryCodeDialog

    d = RecoveryCodeDialog("K7QM-3XR9-PW2H")
    d.show()
    assert not d.ok.isEnabled()
    d.reject()  # Esc no lo cierra todavía
    assert d.isVisible()
    d.done_check.setChecked(True)
    assert d.ok.isEnabled()
    d.ok.click()
    assert not d.isVisible()


def test_olvido_la_clave_desde_la_entrada(app, conn, owner, monkeypatch) -> None:
    import repuestos.ui.recovery_ui as ru
    from repuestos.ui.login import LoginDialog

    code = recovery_service.generate_code(conn, owner)
    shown: list[str] = []
    monkeypatch.setattr(ru.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(ru.RecoveryCodeDialog, "exec", lambda self: shown.append("nuevo"))
    d = ru.RecoverPasswordDialog(conn)
    d.code.setText(code)
    d.password.setText("nueva456")
    d.password2.setText("otra")
    d._save()
    assert "no coinciden" in d.error.text()
    d.password2.setText("nueva456")
    d._save()
    assert d.recovered_username == "yoleida" and shown == ["nuevo"]
    login = LoginDialog(conn, "Romero")
    assert any(b.text() == "¿Olvidó la clave de la dueña?" for b in login.findChildren(ru.QPushButton))


def test_aviso_si_falta_el_codigo(app, conn, owner) -> None:
    from repuestos.ui.main_window import MainWindow

    m = MainWindow(conn, owner)
    m.fetcher.start = lambda: None
    assert "código de recuperación" in m.alerts.text()
    recovery_service.generate_code(conn, owner)
    m.refresh_status()
    assert "código de recuperación" not in m.alerts.text()
    m.close()
