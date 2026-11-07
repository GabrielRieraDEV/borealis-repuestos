"""Recuperación de la clave de la dueña con su código de recuperación.

- El código se muestra una sola vez (al configurar el sistema o cuando la dueña genera uno nuevo) y se guarda solo
  su hash scrypt, como una contraseña.
- Con el código se pone una clave nueva; el código usado deja de servir y se entrega uno nuevo.
- Sin el código no hay forma de hacerlo desde el programa: así ningún vendedor puede tomar la cuenta de la dueña.
  Último recurso (soporte de Borealis, con acceso a la PC): ``python -m repuestos.tools.reset_owner``.
"""

from __future__ import annotations

import sqlite3

from repuestos.db.connection import transaction
from repuestos.db.repositories import settings as settings_repo
from repuestos.db.repositories import users as users_repo
from repuestos.domain.passwords import (
    generate_recovery_code,
    hash_password,
    normalize_recovery_code,
    validate_new_password,
    verify_password,
)
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit

KEY = "owner_recovery_hash"
WRONG_CODE = "El código de recuperación no es correcto. Revise que lo copió completo, en el orden en que lo anotó."


def has_code(conn: sqlite3.Connection) -> bool:
    return bool(settings_repo.get(conn, KEY))


def store_new_code(conn: sqlite3.Connection) -> str:
    code = generate_recovery_code()
    settings_repo.set_value(conn, KEY, hash_password(normalize_recovery_code(code)))
    return code


def generate_code(conn: sqlite3.Connection, owner: User) -> str:
    """Crea un código nuevo (el anterior deja de servir). Devuelve el código para mostrarlo una sola vez."""
    require_owner(owner, "generar el código de recuperación")
    with transaction(conn):
        code = store_new_code(conn)
        audit(conn, owner.id, "RECOVERY_CODE_CREATED", "user", owner.id)
    return code


def reset_owner_password(conn: sqlite3.Connection, code: str, new_password: str) -> tuple[User, str]:
    """Pone una clave nueva a la dueña con el código. Devuelve (dueña, código nuevo para anotar).

    Lanza ValueError con un mensaje claro si el código no sirve o la clave es muy corta.
    """
    validate_new_password(new_password)
    stored = settings_repo.get(conn, KEY)
    owners = [u for u in users_repo.list_all(conn) if u.is_owner and u.active]
    if not stored or not owners:
        raise ValueError("Este sistema no tiene código de recuperación. Comuníquese con Borealis.")
    ok = verify_password(normalize_recovery_code(code), stored)
    with transaction(conn):
        if not ok:
            # Los intentos fallidos quedan registrados; scrypt hace inviable probar códigos a ciegas.
            audit(conn, None, "RECOVERY_FAILED", "user", None)
            failed = True
        else:
            owner = owners[0]
            users_repo.set_password_hash(conn, owner.id, hash_password(new_password))  # también quita el bloqueo
            new_code = store_new_code(conn)  # el código usado ya no sirve
            audit(conn, owner.id, "OWNER_PASSWORD_RECOVERED", "user", owner.id)
            failed = False
    if failed:
        raise ValueError(WRONG_CODE)
    return owner, new_code
