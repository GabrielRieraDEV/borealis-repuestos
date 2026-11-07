"""Repositorio de categorías."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    id: int
    name: str
    active: bool


def list_all(conn: sqlite3.Connection, include_inactive: bool = False) -> list[Category]:
    sql = "SELECT id, name, active FROM categories"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY name COLLATE NOCASE"
    return [Category(r["id"], r["name"], bool(r["active"])) for r in conn.execute(sql)]


def get(conn: sqlite3.Connection, category_id: int) -> Category | None:
    r = conn.execute("SELECT id, name, active FROM categories WHERE id = ?", (category_id,)).fetchone()
    return Category(r["id"], r["name"], bool(r["active"])) if r else None


def find_by_name(conn: sqlite3.Connection, name: str) -> Category | None:
    r = conn.execute("SELECT id, name, active FROM categories WHERE name = ?", (name,)).fetchone()
    return Category(r["id"], r["name"], bool(r["active"])) if r else None


def insert(conn: sqlite3.Connection, name: str) -> int:
    return int(conn.execute("INSERT INTO categories (name) VALUES (?)", (name,)).lastrowid)  # type: ignore[arg-type]


def rename(conn: sqlite3.Connection, category_id: int, name: str) -> None:
    conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))


def set_active(conn: sqlite3.Connection, category_id: int, active: bool) -> None:
    conn.execute("UPDATE categories SET active = ? WHERE id = ?", (int(active), category_id))
