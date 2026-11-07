"""Repositorio de clientes. El id 1 es "Consumidor final"."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from repuestos.domain.money import from_db

FINAL_CONSUMER_ID = 1


@dataclass(frozen=True, slots=True)
class Customer:
    id: int
    name: str
    id_doc: str | None
    phone: str
    credit_enabled: bool
    credit_limit_usd: Decimal | None
    credit_days: int | None
    active: bool

    @property
    def is_final_consumer(self) -> bool:
        return self.id == FINAL_CONSUMER_ID


def _to(r: sqlite3.Row) -> Customer:
    limit = r["credit_limit_usd_e2"]
    return Customer(
        id=r["id"],
        name=r["name"],
        id_doc=r["id_doc"],
        phone=r["phone"],
        credit_enabled=bool(r["credit_enabled"]),
        credit_limit_usd=from_db(limit, "e2") if limit is not None else None,
        credit_days=r["credit_days"],
        active=bool(r["active"]),
    )


def get(conn: sqlite3.Connection, customer_id: int) -> Customer | None:
    r = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return _to(r) if r else None


def get_by_id_doc(conn: sqlite3.Connection, id_doc: str) -> Customer | None:
    r = conn.execute("SELECT * FROM customers WHERE id_doc = ?", (id_doc,)).fetchone()
    return _to(r) if r else None


def search(conn: sqlite3.Connection, text: str, limit: int = 50) -> list[Customer]:
    like = f"%{text}%"
    rows = conn.execute(
        "SELECT * FROM customers WHERE active = 1 AND id <> 1 AND (name LIKE ? OR id_doc LIKE ?)"
        " ORDER BY name COLLATE NOCASE LIMIT ?",
        (like, like, limit),
    )
    return [_to(r) for r in rows]


def insert(conn: sqlite3.Connection, name: str, id_doc: str, phone: str) -> int:
    cur = conn.execute("INSERT INTO customers (name, id_doc, phone) VALUES (?, ?, ?)", (name, id_doc, phone))
    return int(cur.lastrowid)  # type: ignore[arg-type]
