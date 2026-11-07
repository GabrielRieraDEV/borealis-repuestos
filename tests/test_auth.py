import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from repuestos.domain.passwords import hash_password, verify_password
from repuestos.domain.users import Role, require_owner
from repuestos.services import auth_service, setup_service
from repuestos.services.audit_service import audit
from tests.conftest import OWNER_PASSWORD

T0 = datetime(2026, 11, 7, 9, 0, 0)


def _actions(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]


def test_password_hash_roundtrip() -> None:
    h = hash_password("secreto1")
    assert h.startswith("scrypt$16384$8$1$")
    assert verify_password("secreto1", h)
    assert not verify_password("secreto2", h)
    assert not verify_password("secreto1", "basura")
    assert hash_password("secreto1") != h  # sal distinta


def test_setup_creates_owner_and_settings(conn: sqlite3.Connection, owner) -> None:
    assert owner.role is Role.OWNER
    assert not setup_service.needs_setup(conn)
    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    assert settings["business_rif"] == "V-31463591-0"
    assert settings["rounding_multiple_e2"] == "500"
    assert _actions(conn) == ["USER_CREATED", "SETUP_COMPLETED"]
    stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert OWNER_PASSWORD not in stored


def test_setup_runs_only_once(conn: sqlite3.Connection, owner) -> None:
    data = setup_service.SetupData("otra", "Otra", "clave123", "N", "R", "", "", Decimal("5"))
    with pytest.raises(RuntimeError):
        setup_service.complete_setup(conn, data)


@pytest.mark.parametrize(
    "change",
    [
        {"password": "12345"},
        {"owner_username": " "},
        {"business_name": ""},
        {"rounding_multiple": Decimal("0")},
        {"rounding_multiple": Decimal("0.001")},
    ],
)
def test_setup_validation(conn: sqlite3.Connection, change: dict) -> None:
    base = {
        "owner_username": "yoleida",
        "owner_full_name": "Yoleida",
        "password": "clave123",
        "business_name": "Romero",
        "business_rif": "V-1",
        "business_address": "",
        "business_phone": "",
        "rounding_multiple": Decimal("5"),
    }
    with pytest.raises(ValueError):
        setup_service.complete_setup(conn, setup_service.SetupData(**{**base, **change}))
    assert setup_service.needs_setup(conn)


def test_login_ok(conn: sqlite3.Connection, owner) -> None:
    user = auth_service.login(conn, "YOLEIDA", OWNER_PASSWORD, now=T0)  # usuario sin distinguir mayúsculas
    assert user.id == owner.id
    assert _actions(conn)[-1] == "LOGIN"


def test_login_wrong_password(conn: sqlite3.Connection, owner) -> None:
    with pytest.raises(auth_service.AuthError, match="incorrectos"):
        auth_service.login(conn, "yoleida", "mala", now=T0)
    assert conn.execute("SELECT failed_attempts FROM users").fetchone()[0] == 1
    assert _actions(conn)[-1] == "LOGIN_FAILED"


def test_login_unknown_user(conn: sqlite3.Connection, owner) -> None:
    with pytest.raises(auth_service.AuthError, match="incorrectos"):
        auth_service.login(conn, "nadie", "x", now=T0)
    row = conn.execute("SELECT user_id, details_json FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] is None
    assert json.loads(row[1])["username"] == "nadie"


def test_five_failures_lock_for_five_minutes(conn: sqlite3.Connection, owner) -> None:
    for _ in range(4):
        with pytest.raises(auth_service.AuthError, match="incorrectos"):
            auth_service.login(conn, "yoleida", "mala", now=T0)
    with pytest.raises(auth_service.AuthError, match="bloqueado 5 minutos"):
        auth_service.login(conn, "yoleida", "mala", now=T0)
    assert "USER_LOCKED" in _actions(conn)

    # bloqueado aunque la contraseña sea correcta
    with pytest.raises(auth_service.AuthError, match="Intente de nuevo en 3 minutos"):
        auth_service.login(conn, "yoleida", OWNER_PASSWORD, now=T0 + timedelta(minutes=2, seconds=30))

    # a los 5 minutos entra y el contador vuelve a cero
    user = auth_service.login(conn, "yoleida", OWNER_PASSWORD, now=T0 + timedelta(minutes=5, seconds=1))
    assert user.id == owner.id
    assert tuple(conn.execute("SELECT failed_attempts, locked_until FROM users").fetchone()) == (0, None)


def test_success_resets_failed_attempts(conn: sqlite3.Connection, owner) -> None:
    for _ in range(3):
        with pytest.raises(auth_service.AuthError):
            auth_service.login(conn, "yoleida", "mala", now=T0)
    auth_service.login(conn, "yoleida", OWNER_PASSWORD, now=T0)
    assert conn.execute("SELECT failed_attempts FROM users").fetchone()[0] == 0


def test_logout_is_audited(conn: sqlite3.Connection, owner) -> None:
    auth_service.logout(conn, owner)
    assert _actions(conn)[-1] == "LOGOUT"


def test_audit_requires_transaction(conn: sqlite3.Connection, owner) -> None:
    with pytest.raises(RuntimeError):
        audit(conn, owner.id, "X")


def test_require_owner(owner) -> None:
    require_owner(owner)
    from dataclasses import replace

    seller = replace(owner, role=Role.SELLER)
    with pytest.raises(PermissionError):
        require_owner(seller, "cambiar precios")
