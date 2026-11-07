"""Repositorio de configuración clave-valor (tabla ``settings``).

Los valores se guardan como texto; la conversión a Decimal de las claves con escala ocurre aquí.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from repuestos.domain.money import Scale, from_db, to_db


def get_all(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


def get(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise KeyError(f"Configuración desconocida: {key}")
    return row["value"]


def set_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    cur = conn.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    if cur.rowcount != 1:
        raise KeyError(f"Configuración desconocida: {key}")


def get_decimal(conn: sqlite3.Connection, key: str, scale: Scale) -> Decimal:
    return from_db(int(get(conn, key)), scale)


def set_decimal(conn: sqlite3.Connection, key: str, value: Decimal, scale: Scale) -> None:
    set_value(conn, key, str(to_db(value, scale)))
