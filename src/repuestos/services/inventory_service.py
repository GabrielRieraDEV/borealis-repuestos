"""Ajustes (RF-41), conteo físico (RF-42), kardex (RF-16) y "para pedir" (RF-43, RN-10). Solo la dueña."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import inventory as repo
from repuestos.db.repositories import products as products_repo
from repuestos.db.repositories import purchases as purchases_repo
from repuestos.db.repositories.inventory import KardexLine, ToOrderLine
from repuestos.db.repositories.purchases import ProductPurchaseLine
from repuestos.domain.inventory import (
    ADJUSTMENT_MOVEMENT,
    AdjustmentKind,
    MovementType,
    adjustment_qty,
    count_difference,
)
from repuestos.domain.pricing import check_quantity
from repuestos.domain.text import search_words
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit
from repuestos.services.stock import MovementResult, apply_movement

COUNT_LIMIT = 3000


# ------------------------------------------------------------------ ajustes


def adjust(
    conn: sqlite3.Connection,
    user: User,
    product_id: int,
    kind: AdjustmentKind,
    qty: Decimal,
    reason: str,
) -> MovementResult:
    """RF-41: dañado, faltante, uso interno o entrada por corrección. Cantidad y motivo obligatorios.

    El movimiento guarda el costo promedio del momento (RN-13, para valorizar pérdidas).
    """
    require_owner(user, "ajustar el inventario")
    reason = " ".join(reason.split())
    if not reason:
        raise ValueError("Escriba el motivo del ajuste.")
    signed = adjustment_qty(kind, qty)
    with transaction(conn):
        product = products_repo.get(conn, product_id)
        if product is None:
            raise LookupError("El producto no existe.")
        check_quantity(qty, product.data.allows_fraction)
        if product.stock + signed < 0:
            raise ValueError(
                f"{product.code} — {product.name} tiene {product.stock}: no se pueden sacar {qty}. "
                "Si la existencia del sistema está mal, use el conteo físico."
            )
        result = apply_movement(conn, product_id, ADJUSTMENT_MOVEMENT[kind], signed, user.id, reason=reason)
        audit(
            conn,
            user.id,
            "ADJUSTMENT",
            "product",
            product_id,
            {
                "codigo": product.code,
                "tipo": kind.value,
                "cantidad": signed,
                "existencia_antes": result.stock_before,
                "existencia_despues": result.stock_after,
                "costo_usd": result.cost_after,
                "motivo": reason,
            },
        )
    return result


# ------------------------------------------------------------------ conteo físico


@dataclass(frozen=True, slots=True)
class CountRow:
    product_id: int
    code: str
    name: str
    category_name: str
    location: str
    unit: str
    allows_fraction: bool
    stock: Decimal


@dataclass(frozen=True, slots=True)
class CountEntry:
    product_id: int
    counted: Decimal


@dataclass(frozen=True, slots=True)
class CountResult:
    product_id: int
    code: str
    name: str
    system_stock: Decimal
    counted: Decimal
    difference: Decimal


def products_for_count(
    conn: sqlite3.Connection,
    user: User,
    category_id: int | None = None,
    location: str | None = None,
    query: str = "",
) -> list[CountRow]:
    """RF-42: la dueña elige productos por categoría, estante o búsqueda."""
    require_owner(user, "hacer conteos")
    products = products_repo.search(
        conn, search_words(query), None, False, COUNT_LIMIT, category_id=category_id, location=location or None
    )
    return [
        CountRow(
            p.id, p.code, p.name, p.category_name, p.data.location, p.data.unit.value, p.data.allows_fraction, p.stock
        )
        for p in products
    ]


def locations(conn: sqlite3.Connection) -> list[str]:
    return products_repo.locations(conn)


def register_count(
    conn: sqlite3.Connection, user: User, entries: list[CountEntry], note: str = ""
) -> list[CountResult]:
    """RF-42 / RN-09: diferencia = contado − existencia del sistema al guardar; si ≠ 0, un ADJ_COUNT.

    Todo el conteo es una transacción. Devuelve una fila por producto contado (con o sin diferencia).
    """
    require_owner(user, "hacer conteos")
    if not entries:
        raise ValueError("No hay cantidades contadas para guardar.")
    if len({e.product_id for e in entries}) != len(entries):
        raise ValueError("Un producto aparece dos veces en el conteo.")
    reason = "Conteo físico" + (f": {' '.join(note.split())}" if note.strip() else "")
    results: list[CountResult] = []
    with transaction(conn):
        for entry in entries:
            product = products_repo.get(conn, entry.product_id)
            if product is None:
                raise LookupError("Uno de los productos contados no existe.")
            diff = count_difference(entry.counted, product.stock)
            if entry.counted > 0:
                try:
                    check_quantity(entry.counted, product.data.allows_fraction)
                except ValueError as exc:
                    raise ValueError(f"{product.code} — {product.name}: {exc}") from None
            if diff != 0:
                apply_movement(conn, product.id, MovementType.ADJ_COUNT, diff, user.id, reason=reason)
            results.append(CountResult(product.id, product.code, product.name, product.stock, entry.counted, diff))
        differences = [
            {"codigo": r.code, "sistema": r.system_stock, "contado": r.counted, "diferencia": r.difference}
            for r in results
            if r.difference != 0
        ]
        audit(
            conn,
            user.id,
            "STOCK_COUNT",
            "product",
            None,
            {"productos_contados": len(results), "diferencias": differences, "nota": note.strip()},
        )
    return results


# ------------------------------------------------------------------ consultas


def kardex(conn: sqlite3.Connection, user: User, product_id: int) -> list[KardexLine]:
    """RF-16: movimientos del producto (incluye costo: solo la dueña)."""
    require_owner(user, "ver los movimientos con costo")
    return repo.kardex(conn, product_id)


def purchase_history(conn: sqlite3.Connection, user: User, product_id: int) -> list[ProductPurchaseLine]:
    """RF-16: historial de compras del producto."""
    require_owner(user, "ver el historial de compras")
    return purchases_repo.history_for_product(conn, product_id)


def to_order(conn: sqlite3.Connection, user: User) -> list[ToOrderLine]:
    """RF-43 / RN-10: lista "Para pedir" por categoría, con proveedor y costo de la última compra."""
    require_owner(user, "ver la lista para pedir")
    return repo.to_order(conn)
