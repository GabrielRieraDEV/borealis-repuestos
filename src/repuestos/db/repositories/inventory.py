"""Repositorio de movimientos de inventario (kardex) y verificación de existencias (RF-44)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from repuestos.domain.inventory import MovementType, check_movement_sign
from repuestos.domain.money import from_db, to_db


def insert_movement(
    conn: sqlite3.Connection,
    product_id: int,
    kind: MovementType,
    qty: Decimal,
    stock_after: Decimal,
    unit_cost_usd: Decimal,
    user_id: int,
    reason: str = "",
    purchase_id: int | None = None,
    sale_id: int | None = None,
) -> int:
    check_movement_sign(kind, qty)
    cur = conn.execute(
        "INSERT INTO inventory_movements"
        " (product_id, type, qty_e3, stock_after_e3, unit_cost_usd_e4, purchase_id, sale_id, reason, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            product_id,
            kind.value,
            to_db(qty, "e3"),
            to_db(stock_after, "e3"),
            to_db(unit_cost_usd, "e4"),
            purchase_id,
            sale_id,
            reason,
            user_id,
        ),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def has_movements(conn: sqlite3.Connection, product_id: int) -> bool:
    return (
        conn.execute("SELECT 1 FROM inventory_movements WHERE product_id = ? LIMIT 1", (product_id,)).fetchone()
        is not None
    )


@dataclass(frozen=True, slots=True)
class StockMismatch:
    product_id: int
    code: str
    name: str
    stock: Decimal  # products.stock_e3
    ledger: Decimal  # Σ inventory_movements.qty_e3
    last_stock_after: Decimal | None  # stock_after_e3 del último movimiento


def stock_mismatches(conn: sqlite3.Connection) -> list[StockMismatch]:
    """Invariante 1 (docs/03): stock_e3 = Σ qty_e3 y = stock_after_e3 del último movimiento."""
    rows = conn.execute(
        """
        SELECT p.id, p.code, p.name, p.stock_e3,
               COALESCE((SELECT SUM(m.qty_e3) FROM inventory_movements m WHERE m.product_id = p.id), 0) AS ledger,
               (SELECT m.stock_after_e3 FROM inventory_movements m
                 WHERE m.product_id = p.id ORDER BY m.id DESC LIMIT 1) AS last_after
        FROM products p
        """
    ).fetchall()
    out: list[StockMismatch] = []
    for r in rows:
        last_after = r["last_after"]
        if r["stock_e3"] != r["ledger"] or (last_after is not None and last_after != r["stock_e3"]):
            out.append(
                StockMismatch(
                    product_id=r["id"],
                    code=r["code"],
                    name=r["name"],
                    stock=from_db(r["stock_e3"], "e3"),
                    ledger=from_db(r["ledger"], "e3"),
                    last_stock_after=from_db(last_after, "e3") if last_after is not None else None,
                )
            )
    return out
