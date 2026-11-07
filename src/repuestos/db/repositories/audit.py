"""Repositorio de bitácora (``audit_log``). Solo inserta: la bitácora nunca se edita ni se borra."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date


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


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: int
    created_at: str
    user_name: str | None
    authorized_by_name: str | None
    action: str
    entity: str | None
    entity_id: int | None
    details_json: str | None


def search(
    conn: sqlite3.Connection,
    date_from: date | None,
    date_to: date | None,
    user_id: int | None,
    action: str | None,
    limit: int = 2000,
) -> list[AuditEntry]:
    where: list[str] = []
    params: list[object] = []
    if date_from:
        where.append("date(a.created_at) >= ?")
        params.append(date_from.isoformat())
    if date_to:
        where.append("date(a.created_at) <= ?")
        params.append(date_to.isoformat())
    if user_id is not None:
        where.append("(a.user_id = ? OR a.authorized_by = ?)")
        params += [user_id, user_id]
    if action:
        where.append("a.action = ?")
        params.append(action)
    sql = (
        "SELECT a.*, u.full_name AS user_name, o.full_name AS authorized_by_name FROM audit_log a"
        " LEFT JOIN users u ON u.id = a.user_id LEFT JOIN users o ON o.id = a.authorized_by"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.id DESC LIMIT ?"
    return [
        AuditEntry(
            r["id"],
            r["created_at"],
            r["user_name"],
            r["authorized_by_name"],
            r["action"],
            r["entity"],
            r["entity_id"],
            r["details_json"],
        )
        for r in conn.execute(sql, [*params, limit])
    ]


def actions(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT action FROM audit_log ORDER BY action")]
