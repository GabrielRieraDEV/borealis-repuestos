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


@dataclass(frozen=True, slots=True)
class KardexLine:
    id: int
    created_at: str
    kind: MovementType
    qty: Decimal
    stock_after: Decimal
    unit_cost: Decimal
    user_name: str
    reason: str
    purchase_id: int | None
    supplier_invoice: str | None
    supplier_name: str | None
    sale_number: int | None


def kardex(conn: sqlite3.Connection, product_id: int, limit: int = 500) -> list[KardexLine]:
    """Movimientos del producto, del más reciente al más viejo (RF-16)."""
    rows = conn.execute(
        """
        SELECT m.*, u.full_name AS user_name,
               p.supplier_invoice, s.name AS supplier_name, sa.number AS sale_number
        FROM inventory_movements m
        JOIN users u ON u.id = m.user_id
        LEFT JOIN purchases p ON p.id = m.purchase_id
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        LEFT JOIN sales sa ON sa.id = m.sale_id
        WHERE m.product_id = ?
        ORDER BY m.id DESC
        LIMIT ?
        """,
        (product_id, limit),
    )
    return [
        KardexLine(
            id=r["id"],
            created_at=r["created_at"],
            kind=MovementType(r["type"]),
            qty=from_db(r["qty_e3"], "e3"),
            stock_after=from_db(r["stock_after_e3"], "e3"),
            unit_cost=from_db(r["unit_cost_usd_e4"], "e4"),
            user_name=r["user_name"],
            reason=r["reason"],
            purchase_id=r["purchase_id"],
            supplier_invoice=r["supplier_invoice"],
            supplier_name=r["supplier_name"],
            sale_number=r["sale_number"],
        )
        for r in rows
    ]


@dataclass(frozen=True, slots=True)
class ToOrderLine:
    product_id: int
    code: str
    name: str
    brand: str
    category_name: str
    location: str
    allows_fraction: bool
    unit: str
    stock: Decimal
    min_stock: Decimal
    last_supplier: str | None
    last_cost: Decimal | None
    last_purchase_date: str | None


def to_order(conn: sqlite3.Connection) -> list[ToOrderLine]:
    """RN-10: activo, mínimo > 0 y existencia <= mínimo; con proveedor y costo de la última compra no anulada."""
    rows = conn.execute(
        """
        WITH last AS (
            SELECT i.product_id, i.unit_cost_usd_e4, s.name AS supplier_name, p.purchase_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY i.product_id ORDER BY p.purchase_date DESC, p.id DESC, i.id DESC
                   ) AS rn
            FROM purchase_items i
            JOIN purchases p ON p.id = i.purchase_id AND p.status = 'COMPLETED'
            JOIN suppliers s ON s.id = p.supplier_id
        )
        SELECT pr.id, pr.code, pr.name, pr.brand, COALESCE(c.name, '') AS category_name, pr.location,
               pr.allows_fraction, pr.unit, pr.stock_e3, pr.min_stock_e3,
               l.supplier_name, l.unit_cost_usd_e4, l.purchase_date
        FROM products pr
        LEFT JOIN categories c ON c.id = pr.category_id
        LEFT JOIN last l ON l.product_id = pr.id AND l.rn = 1
        WHERE pr.active = 1 AND pr.min_stock_e3 > 0 AND pr.stock_e3 <= pr.min_stock_e3
        ORDER BY COALESCE(c.name, '~') COLLATE NOCASE, pr.name COLLATE NOCASE
        """
    )
    return [
        ToOrderLine(
            product_id=r["id"],
            code=r["code"],
            name=r["name"],
            brand=r["brand"],
            category_name=r["category_name"],
            location=r["location"],
            allows_fraction=bool(r["allows_fraction"]),
            unit=r["unit"],
            stock=from_db(r["stock_e3"], "e3"),
            min_stock=from_db(r["min_stock_e3"], "e3"),
            last_supplier=r["supplier_name"],
            last_cost=from_db(r["unit_cost_usd_e4"], "e4") if r["unit_cost_usd_e4"] is not None else None,
            last_purchase_date=r["purchase_date"],
        )
        for r in rows
    ]
