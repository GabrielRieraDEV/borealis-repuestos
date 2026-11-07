"""Repositorio de tasas de cambio (RN-01)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from repuestos.domain.money import from_db, to_db


class RateSource(StrEnum):
    BCV_AUTO = "BCV_AUTO"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    id: int
    valid_date: date
    rate: Decimal
    source: RateSource
    user_id: int | None
    fetched_at: str


def _to_rate(r: sqlite3.Row) -> ExchangeRate:
    return ExchangeRate(
        id=r["id"],
        valid_date=date.fromisoformat(r["valid_date"]),
        rate=from_db(r["rate_e6"], "e6"),
        source=RateSource(r["source"]),
        user_id=r["user_id"],
        fetched_at=r["fetched_at"],
    )


def current(conn: sqlite3.Connection, today: date) -> ExchangeRate | None:
    """Vigente = la de fecha valor más reciente que sea <= hoy."""
    r = conn.execute(
        "SELECT * FROM exchange_rates WHERE valid_date <= ? ORDER BY valid_date DESC LIMIT 1",
        (today.isoformat(),),
    ).fetchone()
    return _to_rate(r) if r else None


def get_by_date(conn: sqlite3.Connection, valid_date: date) -> ExchangeRate | None:
    r = conn.execute("SELECT * FROM exchange_rates WHERE valid_date = ?", (valid_date.isoformat(),)).fetchone()
    return _to_rate(r) if r else None


def recent(conn: sqlite3.Connection, limit: int = 20) -> list[ExchangeRate]:
    rows = conn.execute("SELECT * FROM exchange_rates ORDER BY valid_date DESC LIMIT ?", (limit,))
    return [_to_rate(r) for r in rows]


def insert(conn: sqlite3.Connection, valid_date: date, rate: Decimal, source: RateSource, user_id: int | None) -> int:
    cur = conn.execute(
        "INSERT INTO exchange_rates (valid_date, rate_e6, source, user_id) VALUES (?, ?, ?, ?)",
        (valid_date.isoformat(), to_db(rate, "e6"), source.value, user_id),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def replace(conn: sqlite3.Connection, rate_id: int, rate: Decimal, source: RateSource, user_id: int | None) -> None:
    conn.execute(
        "UPDATE exchange_rates SET rate_e6 = ?, source = ?, user_id = ?, fetched_at = datetime('now', 'localtime')"
        " WHERE id = ?",
        (to_db(rate, "e6"), source.value, user_id, rate_id),
    )
