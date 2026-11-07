"""Único punto que cambia existencias (invariante 1 de docs/03, RN-09).

Cada cambio escribe el movimiento y actualiza ``products.stock_e3`` (y el costo promedio si cambia) dentro de la
transacción del llamador. Nadie más debe tocar ``stock_e3``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from repuestos.db.repositories import inventory as inventory_repo
from repuestos.db.repositories import products as products_repo
from repuestos.domain.inventory import MovementType


@dataclass(frozen=True, slots=True)
class MovementResult:
    movement_id: int
    stock_before: Decimal
    stock_after: Decimal
    cost_after: Decimal


def apply_movement(
    conn: sqlite3.Connection,
    product_id: int,
    kind: MovementType,
    qty: Decimal,
    user_id: int,
    *,
    new_cost: Decimal | None = None,
    reason: str = "",
    purchase_id: int | None = None,
    sale_id: int | None = None,
) -> MovementResult:
    """Aplica un movimiento con signo. ``new_cost`` solo cuando el costo promedio cambia (compras, RN-08).

    El movimiento guarda el costo promedio del momento, ya aplicado (RN-13).
    """
    if not conn.in_transaction:
        raise RuntimeError("apply_movement debe llamarse dentro de una transacción")
    product = products_repo.get(conn, product_id)
    if product is None:
        raise LookupError("El producto no existe.")
    before = product.stock
    after = before + qty
    cost = product.data.cost_usd if new_cost is None else new_cost
    movement_id = inventory_repo.insert_movement(
        conn, product_id, kind, qty, after, cost, user_id, reason=reason, purchase_id=purchase_id, sale_id=sale_id
    )
    products_repo.set_stock(conn, product_id, after)
    if new_cost is not None and new_cost != product.data.cost_usd:
        products_repo.set_cost(conn, product_id, new_cost)
    return MovementResult(movement_id, before, after, cost)
