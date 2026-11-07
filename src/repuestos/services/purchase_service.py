"""Compras (RF-30 a RF-32) y proveedores. Solo la dueña.

Registrar compra = una transacción: purchases, purchase_items, inventory_movements(PURCHASE), products (existencia
y costo promedio, RN-08 en el orden de los renglones), audit_log.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import products as products_repo
from repuestos.db.repositories import purchases as repo
from repuestos.db.repositories import suppliers as suppliers_repo
from repuestos.db.repositories.purchases import Purchase
from repuestos.db.repositories.suppliers import Supplier
from repuestos.domain.inventory import MovementType
from repuestos.domain.money import ZERO, hu
from repuestos.domain.pricing import check_quantity, purchase_line_total, weighted_average_cost
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit
from repuestos.services.stock import apply_movement


@dataclass(frozen=True, slots=True)
class PurchaseLineInput:
    product_id: int
    qty: Decimal
    unit_cost: Decimal


# ------------------------------------------------------------------ proveedores


def list_suppliers(conn: sqlite3.Connection) -> list[Supplier]:
    return suppliers_repo.list_all(conn)


def create_supplier(conn: sqlite3.Connection, user: User, name: str, rif: str = "", phone: str = "") -> Supplier:
    """Alta rápida desde la compra."""
    require_owner(user, "crear proveedores")
    name = " ".join(name.split())
    if not name:
        raise ValueError("Escriba el nombre del proveedor.")
    with transaction(conn):
        if suppliers_repo.find_by_name(conn, name) is not None:
            raise ValueError(f"Ya existe el proveedor «{name}».")
        supplier_id = suppliers_repo.insert(conn, name, rif.strip().upper(), phone.strip())
        audit(conn, user.id, "SUPPLIER_CREATED", "supplier", supplier_id, {"nombre": name})
    supplier = suppliers_repo.get(conn, supplier_id)
    assert supplier is not None
    return supplier


# ------------------------------------------------------------------ compras


def _check_line(line: PurchaseLineInput) -> None:
    if line.qty <= 0:
        raise ValueError("La cantidad de cada renglón debe ser mayor que cero.")
    if line.qty != hu(line.qty, 3):
        raise ValueError("La cantidad admite como máximo 3 decimales.")
    if line.unit_cost < 0:
        raise ValueError("El costo no puede ser negativo.")
    if line.unit_cost != hu(line.unit_cost, 4):
        raise ValueError("El costo unitario admite como máximo 4 decimales.")


def register_purchase(
    conn: sqlite3.Connection,
    user: User,
    supplier_id: int,
    lines: list[PurchaseLineInput],
    purchase_date: date,
    supplier_invoice: str = "",
    notes: str = "",
    today: date | None = None,
) -> Purchase:
    """RF-30. Si el mismo producto aparece dos veces, el costo promedio se aplica dos veces, en orden (RN-08)."""
    require_owner(user, "registrar compras")
    if not lines:
        raise ValueError("Agregue al menos un producto a la compra.")
    if purchase_date > (today or date.today()):
        raise ValueError("La fecha de la compra no puede ser futura.")
    for line in lines:
        _check_line(line)
    totals = [purchase_line_total(line.qty, line.unit_cost) for line in lines]

    with transaction(conn):
        supplier = suppliers_repo.get(conn, supplier_id)
        if supplier is None or not supplier.active:
            raise ValueError("Elija un proveedor.")
        for line in lines:
            product = products_repo.get(conn, line.product_id)
            if product is None:
                raise LookupError("Uno de los productos de la compra no existe.")
            if not product.active:
                raise ValueError(f"El producto {product.code} — {product.name} está inactivo. Actívelo primero.")
            check_quantity(line.qty, product.data.allows_fraction)

        purchase_id = repo.insert(
            conn, supplier_id, supplier_invoice.strip(), purchase_date, sum(totals, ZERO), notes.strip(), user.id
        )
        cost_changes: list[dict[str, object]] = []
        for line, line_total in zip(lines, totals, strict=True):
            product = products_repo.get(conn, line.product_id)
            assert product is not None
            new_cost = weighted_average_cost(product.stock, product.data.cost_usd, line.qty, line.unit_cost)
            repo.insert_item(conn, purchase_id, line.product_id, line.qty, line.unit_cost, line_total)
            apply_movement(
                conn,
                line.product_id,
                MovementType.PURCHASE,
                line.qty,
                user.id,
                new_cost=new_cost,
                purchase_id=purchase_id,
            )
            cost_changes.append(
                {
                    "codigo": product.code,
                    "cantidad": line.qty,
                    "costo_compra": line.unit_cost,
                    "costo_antes": product.data.cost_usd,
                    "costo_despues": new_cost,
                }
            )
        audit(
            conn,
            user.id,
            "PURCHASE_CREATED",
            "purchase",
            purchase_id,
            {
                "proveedor": supplier.name,
                "factura": supplier_invoice.strip(),
                "total_usd": sum(totals, ZERO),
                "renglones": cost_changes,
            },
        )
    purchase = repo.get(conn, purchase_id)
    assert purchase is not None
    return purchase


def void_purchase(conn: sqlite3.Connection, user: User, purchase_id: int, reason: str) -> None:
    """RF-31 / RN-14: resta lo que la compra sumó, sin recalcular el costo. Bloquea si deja existencias negativas."""
    require_owner(user, "anular compras")
    reason = " ".join(reason.split())
    if not reason:
        raise ValueError("Escriba el motivo de la anulación.")
    with transaction(conn):
        purchase = repo.get(conn, purchase_id)
        if purchase is None:
            raise LookupError("La compra no existe.")
        if purchase.voided:
            raise ValueError("Esta compra ya está anulada.")
        per_product: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for item in purchase.items:
            per_product[item.product_id] += item.qty
        for product_id, qty in per_product.items():
            product = products_repo.get(conn, product_id)
            assert product is not None
            if product.stock - qty < 0:
                raise ValueError(
                    f"No se puede anular: {product.code} — {product.name} quedaría con existencia "
                    f"{product.stock - qty} (hoy tiene {product.stock}). Corrija con un ajuste si hace falta."
                )
        for item in purchase.items:
            apply_movement(
                conn,
                item.product_id,
                MovementType.PURCHASE_VOID,
                -item.qty,
                user.id,
                reason=reason,
                purchase_id=purchase_id,
            )
        repo.set_voided(conn, purchase_id, user.id, reason)
        audit(
            conn,
            user.id,
            "PURCHASE_VOID",
            "purchase",
            purchase_id,
            {"proveedor": purchase.supplier_name, "total_usd": purchase.total_usd, "motivo": reason},
        )


def list_purchases(
    conn: sqlite3.Connection,
    user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    supplier_id: int | None = None,
    product_id: int | None = None,
) -> list[Purchase]:
    """RF-32: lista con filtro por fecha, proveedor y producto."""
    require_owner(user, "ver las compras")
    return repo.search(conn, date_from, date_to, supplier_id, product_id)


def get_purchase(conn: sqlite3.Connection, user: User, purchase_id: int) -> Purchase:
    require_owner(user, "ver las compras")
    purchase = repo.get(conn, purchase_id)
    if purchase is None:
        raise LookupError("La compra no existe.")
    return purchase
