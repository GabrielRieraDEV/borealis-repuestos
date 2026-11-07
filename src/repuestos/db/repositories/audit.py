"""Repositorio de bitácora (``audit_log``). Solo inserta: la bitácora nunca se edita ni se borra."""

from __future__ import annotations

import sqlite3


def insert(
    conn: sqlite3.Connection,
    user_id: int | None,
    action: str,
    entity: str | None,
    entity_id: int | None,
    details_json: str | None,
    authorized_by: int | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO audit_log (user_id, authorized_by, action, entity, entity_id, details_json)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, authorized_by, action, entity, entity_id, details_json),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]
