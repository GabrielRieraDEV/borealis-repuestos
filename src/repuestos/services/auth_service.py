"""Inicio de sesión (RF-01): scrypt, 5 intentos fallidos bloquean al usuario 5 minutos."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta

from repuestos.db.connection import transaction
from repuestos.db.repositories import users as users_repo
from repuestos.domain.passwords import verify_password
from repuestos.domain.users import User
from repuestos.services.audit_service import audit

MAX_ATTEMPTS = 5
LOCK_MINUTES = 5
TIME_FMT = "%Y-%m-%d %H:%M:%S"

WRONG_CREDENTIALS = "Usuario o contraseña incorrectos."


class AuthError(Exception):
    """Error de inicio de sesión con un mensaje listo para mostrar."""


def login(conn: sqlite3.Connection, username: str, password: str, now: datetime | None = None) -> User:
    now = now or datetime.now()
    username = username.strip()
    error: str | None = None
    user: User | None = None

    # Los intentos fallidos también se guardan: la transacción se confirma y el error se lanza después.
    with transaction(conn):
        row = users_repo.get_auth(conn, username) if username else None
        if row is None or not row.user.active:
            audit(conn, None, "LOGIN_FAILED", "user", None, {"username": username, "reason": "unknown_or_inactive"})
            error = WRONG_CREDENTIALS
        elif row.locked_until and datetime.strptime(row.locked_until, TIME_FMT) > now:
            remaining = datetime.strptime(row.locked_until, TIME_FMT) - now
            minutes = max(1, math.ceil(remaining.total_seconds() / 60))
            audit(conn, row.user.id, "LOGIN_FAILED", "user", row.user.id, {"reason": "locked"})
            error = (
                "Este usuario está bloqueado por varios intentos fallidos. "
                f"Intente de nuevo en {minutes} minuto{'s' if minutes != 1 else ''}."
            )
        elif not verify_password(password, row.password_hash):
            attempts = row.failed_attempts + 1
            if attempts >= MAX_ATTEMPTS:
                locked_until = (now + timedelta(minutes=LOCK_MINUTES)).strftime(TIME_FMT)
                users_repo.set_login_failure(conn, row.user.id, 0, locked_until)
                audit(conn, row.user.id, "USER_LOCKED", "user", row.user.id, {"until": locked_until})
                error = (
                    f"Contraseña incorrecta {MAX_ATTEMPTS} veces. "
                    f"El usuario quedó bloqueado {LOCK_MINUTES} minutos."
                )
            else:
                users_repo.set_login_failure(conn, row.user.id, attempts, None)
                error = WRONG_CREDENTIALS
            audit(conn, row.user.id, "LOGIN_FAILED", "user", row.user.id, {"attempt": attempts})
        else:
            users_repo.reset_login_state(conn, row.user.id)
            audit(conn, row.user.id, "LOGIN", "user", row.user.id)
            user = row.user

    if error is not None:
        raise AuthError(error)
    assert user is not None
    return user


def logout(conn: sqlite3.Connection, user: User) -> None:
    with transaction(conn):
        audit(conn, user.id, "LOGOUT", "user", user.id)
