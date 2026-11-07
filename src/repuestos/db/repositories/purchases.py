"""Repositorio de compras y sus renglones."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.domain.money import from_db, to_db


@dataclass(frozen=True, slots=True)
class PurchaseItem:
    id: int
    product_id: int
    product_code: str
    product_name: str
    qty: Decimal
    unit_cost: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class Purchase:
    id: int
    supplier_id: int
    supplier_name: str
    supplier_invoice: str
    purchase_date: date
    total_usd: Decimal
    notes: str
    status: str
    user_id: int
    voided_at: str | None
    void_reason: str | None
    created_at: str
    items: tuple[PurchaseItem, ...] = ()

    @property
    def voided(self) -> bool:
        return self.status == "VOIDED"


_SELECT = """
SELECT p.*, s.name AS supplier_name
FROM purchases p JOIN suppliers s ON s.id = p.supplier_id
"""


def _to(r: sqlite3.Row, items: tuple[PurchaseItem, ...] = ()) -> Purchase:
    return Purchase(
        id=r["id"],
        supplier_id=r["supplier_id"],
        supplier_name=r["supplier_name"],
        supplier_invoice=r["supplier_invoice"],
        purchase_date=date.fromisoformat(r["purchase_date"]),
        total_usd=from_db(r["total_usd_e2"], "e2"),
        notes=r["notes"],
        status=r["status"],
        user_id=r["user_id"],
        voided_at=r["voided_at"],
        void_reason=r["void_reason"],
        created_at=r["created_at"],
        items=items,
    )


def insert(
    conn: sqlite3.Connection,
    supplier_id: int,
    supplier_invoice: str,
    purchase_date: date,
    total_usd: Decimal,
    notes: str,
    user_id: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO purchases (supplier_id, supplier_invoice, purchase_date, total_usd_e2, notes, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (supplier_id, supplier_invoice, purchase_date.isoformat(), to_db(total_usd, "e2"), notes, user_id),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def insert_item(
    conn: sqlite3.Connection, purchase_id: int, product_id: int, qty: Decimal, unit_cost: Decimal, line_total: Decimal
) -> int:
    cur = conn.execute(
        "INSERT INTO purchase_items (purchase_id, product_id, qty_e3, unit_cost_usd_e4, line_total_usd_e2)"
        " VALUES (?, ?, ?, ?, ?)",
        (purchase_id, product_id, to_db(qty, "e3"), to_db(unit_cost, "e4"), to_db(line_total, "e2")),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def items(conn: sqlite3.Connection, purchase_id: int) -> tuple[PurchaseItem, ...]:
    rows = conn.execute(
        "SELECT i.*, p.code, p.name FROM purchase_items i JOIN products p ON p.id = i.product_id"
        " WHERE i.purchase_id = ? ORDER BY i.id",
        (purchase_id,),
    )
    return tuple(
        PurchaseItem(
            id=r["id"],
            product_id=r["product_id"],
            product_code=r["code"],
            product_name=r["name"],
            qty=from_db(r["qty_e3"], "e3"),
            unit_cost=from_db(r["unit_cost_usd_e4"], "e4"),
            line_total=from_db(r["line_total_usd_e2"], "e2"),
        )
        for r in rows
    )


def get(conn: sqlite3.Connection, purchase_id: int) -> Purchase | None:
    r = conn.execute(_SELECT + " WHERE p.id = ?", (purchase_id,)).fetchone()
    return _to(r, items(conn, purchase_id)) if r else None


def search(
    conn: sqlite3.Connection,
    date_from: date | None,
    date_to: date | None,
    supplier_id: int | None,
    product_id: int | None,
    limit: int = 500,
) -> list[Purchase]:
    where: list[str] = []
    params: list[object] = []
    if date_from:
        where.append("p.purchase_date >= ?")
        params.append(date_from.isoformat())
    if date_to:
        where.append("p.purchase_date <= ?")
        params.append(date_to.isoformat())
    if supplier_id:
        where.append("p.supplier_id = ?")
        params.append(supplier_id)
    if product_id:
        where.append("EXISTS (SELECT 1 FROM purchase_items i WHERE i.purchase_id = p.id AND i.product_id = ?)")
        params.append(product_id)
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY p.purchase_date DESC, p.id DESC LIMIT ?"
    return [_to(r) for r in conn.execute(sql, [*params, limit])]


def set_voided(conn: sqlite3.Connection, purchase_id: int, user_id: int, reason: str) -> None:
    conn.execute(
        "UPDATE purchases SET status = 'VOIDED', voided_by = ?, voided_at = datetime('now', 'localtime'),"
        " void_reason = ? WHERE id = ?",
        (user_id, reason, purchase_id),
    )


@dataclass(frozen=True, slots=True)
class ProductPurchaseLine:
    purchase_id: int
    purchase_date: date
    supplier_name: str
    supplier_invoice: str
    qty: Decimal
    unit_cost: Decimal
    voided: bool


def history_for_product(conn: sqlite3.Connection, product_id: int, limit: int = 200) -> list[ProductPurchaseLine]:
    rows = conn.execute(
        """
        SELECT p.id, p.purchase_date, s.name AS supplier_name, p.supplier_invoice, p.status,
               i.qty_e3, i.unit_cost_usd_e4
        FROM purchase_items i
        JOIN purchases p ON p.id = i.purchase_id
        JOIN suppliers s ON s.id = p.supplier_id
        WHERE i.product_id = ?
        ORDER BY p.purchase_date DESC, p.id DESC, i.id DESC
        LIMIT ?
        """,
        (product_id, limit),
    )
    return [
        ProductPurchaseLine(
            purchase_id=r["id"],
            purchase_date=date.fromisoformat(r["purchase_date"]),
            supplier_name=r["supplier_name"],
            supplier_invoice=r["supplier_invoice"],
            qty=from_db(r["qty_e3"], "e3"),
            unit_cost=from_db(r["unit_cost_usd_e4"], "e4"),
            voided=r["status"] == "VOIDED",
        )
        for r in rows
    ]
