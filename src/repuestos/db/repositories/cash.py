"""Repositorio de caja: sesiones, entradas/salidas y sumas para el arqueo (RN-11)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from repuestos.domain.money import from_db, to_db


@dataclass(frozen=True, slots=True)
class CashSession:
    id: int
    status: str
    opened_by: int
    opened_by_name: str
    opened_at: str
    opening_usd: Decimal
    opening_ves: Decimal
    closed_by: int | None
    closed_by_name: str | None
    closed_at: str | None
    expected_usd: Decimal | None
    expected_ves: Decimal | None
    counted_usd: Decimal | None
    counted_ves: Decimal | None
    notes: str

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN"


@dataclass(frozen=True, slots=True)
class CashMovement:
    id: int
    direction: str
    currency: str
    amount: Decimal
    reason: str
    user_name: str
    created_at: str


_SELECT = """
SELECT s.*, uo.full_name AS opened_by_name, uc.full_name AS closed_by_name
FROM cash_sessions s
JOIN users uo ON uo.id = s.opened_by
LEFT JOIN users uc ON uc.id = s.closed_by
"""


def _opt(value: int | None) -> Decimal | None:
    return from_db(value, "e2") if value is not None else None


def _to(r: sqlite3.Row) -> CashSession:
    return CashSession(
        id=r["id"],
        status=r["status"],
        opened_by=r["opened_by"],
        opened_by_name=r["opened_by_name"],
        opened_at=r["opened_at"],
        opening_usd=from_db(r["opening_usd_e2"], "e2"),
        opening_ves=from_db(r["opening_ves_e2"], "e2"),
        closed_by=r["closed_by"],
        closed_by_name=r["closed_by_name"],
        closed_at=r["closed_at"],
        expected_usd=_opt(r["expected_usd_e2"]),
        expected_ves=_opt(r["expected_ves_e2"]),
        counted_usd=_opt(r["counted_usd_e2"]),
        counted_ves=_opt(r["counted_ves_e2"]),
        notes=r["notes"],
    )


def get_open(conn: sqlite3.Connection) -> CashSession | None:
    r = conn.execute(_SELECT + " WHERE s.status = 'OPEN'").fetchone()
    return _to(r) if r else None


def get(conn: sqlite3.Connection, session_id: int) -> CashSession | None:
    r = conn.execute(_SELECT + " WHERE s.id = ?", (session_id,)).fetchone()
    return _to(r) if r else None


def history(conn: sqlite3.Connection, limit: int = 200) -> list[CashSession]:
    return [_to(r) for r in conn.execute(_SELECT + " ORDER BY s.id DESC LIMIT ?", (limit,))]


def insert(conn: sqlite3.Connection, user_id: int, opening_usd: Decimal, opening_ves: Decimal) -> int:
    cur = conn.execute(
        "INSERT INTO cash_sessions (opened_by, opening_usd_e2, opening_ves_e2) VALUES (?, ?, ?)",
        (user_id, to_db(opening_usd, "e2"), to_db(opening_ves, "e2")),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def close(
    conn: sqlite3.Connection,
    session_id: int,
    user_id: int,
    expected_usd: Decimal,
    expected_ves: Decimal,
    counted_usd: Decimal,
    counted_ves: Decimal,
    notes: str,
) -> None:
    conn.execute(
        "UPDATE cash_sessions SET status = 'CLOSED', closed_by = ?, closed_at = datetime('now', 'localtime'),"
        " expected_usd_e2 = ?, expected_ves_e2 = ?, counted_usd_e2 = ?, counted_ves_e2 = ?, notes = ?"
        " WHERE id = ? AND status = 'OPEN'",
        (
            user_id,
            to_db(expected_usd, "e2"),
            to_db(expected_ves, "e2"),
            to_db(counted_usd, "e2"),
            to_db(counted_ves, "e2"),
            notes,
            session_id,
        ),
    )


def insert_movement(
    conn: sqlite3.Connection, session_id: int, direction: str, currency: str, amount: Decimal, reason: str, user_id: int
) -> int:
    cur = conn.execute(
        "INSERT INTO cash_movements (session_id, direction, currency, amount_e2, reason, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, direction, currency, to_db(amount, "e2"), reason, user_id),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def movements(conn: sqlite3.Connection, session_id: int) -> list[CashMovement]:
    rows = conn.execute(
        "SELECT m.*, u.full_name FROM cash_movements m JOIN users u ON u.id = m.user_id"
        " WHERE m.session_id = ? ORDER BY m.id",
        (session_id,),
    )
    return [
        CashMovement(
            r["id"],
            r["direction"],
            r["currency"],
            from_db(r["amount_e2"], "e2"),
            r["reason"],
            r["full_name"],
            r["created_at"],
        )
        for r in rows
    ]


def sum_payments(conn: sqlite3.Connection, session_id: int, method: str) -> tuple[Decimal, int]:
    """Σ amount_e2 de pagos no anulados de la sesión (ventas y abonos, vuelto negativo incluido) y nº de cobros."""
    r = conn.execute(
        "SELECT COALESCE(SUM(amount_e2), 0), COUNT(CASE WHEN is_change = 0 THEN 1 END) FROM payments"
        " WHERE session_id = ? AND method = ? AND voided = 0",
        (session_id, method),
    ).fetchone()
    return from_db(r[0], "e2"), int(r[1])


def sum_movements(conn: sqlite3.Connection, session_id: int, direction: str, currency: str) -> Decimal:
    r = conn.execute(
        "SELECT COALESCE(SUM(amount_e2), 0) FROM cash_movements"
        " WHERE session_id = ? AND direction = ? AND currency = ?",
        (session_id, direction, currency),
    ).fetchone()
    return from_db(r[0], "e2")


def sales_counts(conn: sqlite3.Connection, session_id: int) -> tuple[int, int, Decimal]:
    """(ventas completadas, ventas anuladas, total Bs de las completadas)."""
    r = conn.execute(
        "SELECT COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END), COUNT(CASE WHEN status = 'VOIDED' THEN 1 END),"
        " COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN total_ves_e2 END), 0)"
        " FROM sales WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return int(r[0]), int(r[1]), from_db(r[2], "e2")
