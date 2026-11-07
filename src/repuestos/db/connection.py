"""Conexión SQLite y transacciones.

PRAGMA de CLAUDE.md: WAL, synchronous=FULL (en el local se va la luz), foreign_keys, busy_timeout.
La conexión trabaja en modo autocommit de Python (``isolation_level=None``): las transacciones se abren
explícitamente con ``transaction()``, que usa ``BEGIN IMMEDIATE`` y revierte ante cualquier excepción.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    if str(path) != ":memory:" and mode.lower() != "wal":
        conn.close()
        raise RuntimeError(f"No se pudo activar el modo WAL en la base de datos (modo actual: {mode}).")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Una operación de negocio = una transacción. Rollback ante cualquier excepción."""
    if conn.in_transaction:
        raise RuntimeError("Ya hay una transacción abierta en esta conexión (transacción anidada).")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
