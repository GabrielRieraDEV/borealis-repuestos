"""Usuarios (RF-03) y autorización con la clave de la dueña (RF-04)."""

from __future__ import annotations

import sqlite3

from repuestos.db.connection import transaction
from repuestos.db.repositories import users as repo
from repuestos.domain.passwords import hash_password, validate_new_password, verify_password
from repuestos.domain.users import Role, User, require_owner
from repuestos.services.audit_service import audit


def list_users(conn: sqlite3.Connection, user: User) -> list[User]:
    require_owner(user, "ver los usuarios")
    return repo.list_all(conn)


def create_seller(conn: sqlite3.Connection, owner: User, username: str, full_name: str, password: str) -> User:
    require_owner(owner, "crear usuarios")
    username = username.strip()
    full_name = " ".join(full_name.split())
    if not username:
        raise ValueError("Escriba el nombre de usuario.")
    if " " in username:
        raise ValueError("El nombre de usuario no puede tener espacios.")
    if not full_name:
        raise ValueError("Escriba el nombre completo.")
    validate_new_password(password)
    with transaction(conn):
        if repo.get_auth(conn, username) is not None:
            raise ValueError(f"Ya existe el usuario «{username}».")
        user_id = repo.insert(conn, username, full_name, Role.SELLER, hash_password(password))
        audit(conn, owner.id, "USER_CREATED", "user", user_id, {"usuario": username, "rol": "seller"})
    created = repo.get(conn, user_id)
    assert created is not None
    return created


def set_active(conn: sqlite3.Connection, owner: User, user_id: int, active: bool) -> None:
    require_owner(owner, "activar o desactivar usuarios")
    with transaction(conn):
        target = repo.get(conn, user_id)
        if target is None:
            raise LookupError("El usuario no existe.")
        if target.is_owner:
            raise ValueError("La cuenta de la dueña no se puede desactivar.")
        if target.active == active:
            return
        repo.set_active(conn, user_id, active)
        audit(
            conn,
            owner.id,
            "USER_ACTIVATED" if active else "USER_DEACTIVATED",
            "user",
            user_id,
            {"usuario": target.username},
        )


def reset_password(conn: sqlite3.Connection, owner: User, user_id: int, new_password: str) -> None:
    """La dueña restablece la contraseña de un vendedor (o la suya). También quita el bloqueo."""
    require_owner(owner, "restablecer contraseñas")
    validate_new_password(new_password)
    with transaction(conn):
        target = repo.get(conn, user_id)
        if target is None:
            raise LookupError("El usuario no existe.")
        if target.is_owner and target.id != owner.id:
            raise PermissionError("No se puede cambiar la contraseña de otra dueña.")
        repo.set_password_hash(conn, user_id, hash_password(new_password))
        audit(conn, owner.id, "USER_PASSWORD_RESET", "user", user_id, {"usuario": target.username})


def authorize_owner(conn: sqlite3.Connection, password: str, requested_by: User, action: str) -> int | None:
    """RF-04: verifica la clave de la dueña. Devuelve el id de la dueña o None.

    El uso de la autorización lo registra la acción autorizada (``authorized_by`` en su bitácora).
    Aquí solo se registran los intentos fallidos.
    """
    for owner_id, password_hash in repo.active_owner_hashes(conn):
        if verify_password(password, password_hash):
            return owner_id
    with transaction(conn):
        audit(conn, requested_by.id, "AUTHORIZATION_FAILED", None, None, {"accion": action})
    return None
