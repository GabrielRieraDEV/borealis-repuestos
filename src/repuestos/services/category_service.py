"""Categorías editables (RF-14)."""

from __future__ import annotations

import sqlite3

from repuestos.db.connection import transaction
from repuestos.db.repositories import categories as repo
from repuestos.db.repositories import products as products_repo
from repuestos.db.repositories.categories import Category
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit
from repuestos.services.product_service import regenerate_search_text


def list_categories(conn: sqlite3.Connection, include_inactive: bool = False) -> list[Category]:
    return repo.list_all(conn, include_inactive)


def _clean(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise ValueError("Escriba el nombre de la categoría.")
    return name


def create_category(conn: sqlite3.Connection, user: User, name: str) -> int:
    require_owner(user, "crear categorías")
    name = _clean(name)
    with transaction(conn):
        existing = repo.find_by_name(conn, name)
        if existing is not None:
            if existing.active:
                raise ValueError(f"Ya existe la categoría «{existing.name}».")
            repo.set_active(conn, existing.id, True)
            audit(conn, user.id, "CATEGORY_ACTIVATED", "category", existing.id, {"nombre": existing.name})
            return existing.id
        category_id = repo.insert(conn, name)
        audit(conn, user.id, "CATEGORY_CREATED", "category", category_id, {"nombre": name})
        return category_id


def rename_category(conn: sqlite3.Connection, user: User, category_id: int, name: str) -> None:
    require_owner(user, "cambiar categorías")
    name = _clean(name)
    with transaction(conn):
        old = repo.get(conn, category_id)
        if old is None:
            raise LookupError("La categoría no existe.")
        if old.name == name:
            return
        other = repo.find_by_name(conn, name)
        if other is not None and other.id != category_id:
            raise ValueError(f"Ya existe la categoría «{other.name}».")
        repo.rename(conn, category_id, name)
        regenerate_search_text(conn, products_repo.ids_in_category(conn, category_id))
        audit(conn, user.id, "CATEGORY_RENAMED", "category", category_id, {"antes": old.name, "despues": name})


def set_active(conn: sqlite3.Connection, user: User, category_id: int, active: bool) -> None:
    """Una categoría inactiva no se ofrece para productos nuevos; los productos que la tienen la conservan."""
    require_owner(user, "activar o desactivar categorías")
    with transaction(conn):
        old = repo.get(conn, category_id)
        if old is None:
            raise LookupError("La categoría no existe.")
        if old.active == active:
            return
        repo.set_active(conn, category_id, active)
        audit(
            conn,
            user.id,
            "CATEGORY_ACTIVATED" if active else "CATEGORY_DEACTIVATED",
            "category",
            category_id,
            {"nombre": old.name},
        )
