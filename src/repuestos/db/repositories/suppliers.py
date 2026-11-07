"""Repositorio de proveedores."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Supplier:
    id: int
    name: str
    rif: str
    phone: str
    active: bool


def _to(r: sqlite3.Row) -> Supplier:
    return Supplier(r["id"], r["name"], r["rif"], r["phone"], bool(r["active"]))


def list_all(conn: sqlite3.Connection, include_inactive: bool = False) -> list[Supplier]:
    sql = "SELECT * FROM suppliers" + ("" if include_inactive else " WHERE active = 1")
    return [_to(r) for r in conn.execute(sql + " ORDER BY name COLLATE NOCASE")]


def get(conn: sqlite3.Connection, supplier_id: int) -> Supplier | None:
    r = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    return _to(r) if r else None


def find_by_name(conn: sqlite3.Connection, name: str) -> Supplier | None:
    r = conn.execute("SELECT * FROM suppliers WHERE name = ?", (name,)).fetchone()
    return _to(r) if r else None


def insert(conn: sqlite3.Connection, name: str, rif: str, phone: str) -> int:
    cur = conn.execute("INSERT INTO suppliers (name, rif, phone) VALUES (?, ?, ?)", (name, rif, phone))
    return int(cur.lastrowid)  # type: ignore[arg-type]
