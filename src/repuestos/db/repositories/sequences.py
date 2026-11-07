"""Correlativos sin saltos (RN-12): se toman dentro de la transacción del documento."""

from __future__ import annotations

import sqlite3


def take_next(conn: sqlite3.Connection, doc_type: str) -> int:
    """Devuelve el número a usar y aumenta el contador. Si la transacción se revierte, el número no se pierde."""
    if not conn.in_transaction:
        raise RuntimeError("Los correlativos se toman dentro de la transacción del documento")
    row = conn.execute(
        "UPDATE doc_sequences SET next_number = next_number + 1 WHERE doc_type = ? RETURNING next_number - 1",
        (doc_type,),
    ).fetchone()
    if row is None:
        raise LookupError(f"No existe el correlativo {doc_type}")
    return int(row[0])
