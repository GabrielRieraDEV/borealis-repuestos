"""Movimientos de inventario y su signo (RN-09)."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class MovementType(StrEnum):
    INITIAL = "INITIAL"
    PURCHASE = "PURCHASE"
    PURCHASE_VOID = "PURCHASE_VOID"
    SALE = "SALE"
    SALE_VOID = "SALE_VOID"
    ADJ_COUNT = "ADJ_COUNT"
    ADJ_DAMAGE = "ADJ_DAMAGE"
    ADJ_MISSING = "ADJ_MISSING"
    ADJ_INTERNAL_USE = "ADJ_INTERNAL_USE"
    ADJ_CORRECTION_IN = "ADJ_CORRECTION_IN"


POSITIVE = {MovementType.INITIAL, MovementType.PURCHASE, MovementType.SALE_VOID, MovementType.ADJ_CORRECTION_IN}
NEGATIVE = {
    MovementType.PURCHASE_VOID,
    MovementType.SALE,
    MovementType.ADJ_DAMAGE,
    MovementType.ADJ_MISSING,
    MovementType.ADJ_INTERNAL_USE,
}

MOVEMENT_LABELS = {
    MovementType.INITIAL: "Existencia inicial",
    MovementType.PURCHASE: "Compra",
    MovementType.PURCHASE_VOID: "Compra anulada",
    MovementType.SALE: "Venta",
    MovementType.SALE_VOID: "Venta anulada",
    MovementType.ADJ_COUNT: "Conteo",
    MovementType.ADJ_DAMAGE: "Dañado",
    MovementType.ADJ_MISSING: "Faltante",
    MovementType.ADJ_INTERNAL_USE: "Uso interno",
    MovementType.ADJ_CORRECTION_IN: "Entrada por corrección",
}


def check_movement_sign(kind: MovementType, qty: Decimal) -> None:
    """RN-09: la cantidad lleva el signo del tipo de movimiento (también es CHECK en la base)."""
    if qty == 0:
        raise ValueError("Un movimiento de inventario no puede tener cantidad cero.")
    if kind in POSITIVE and qty < 0:
        raise ValueError(f"El movimiento {kind} debe sumar existencia.")
    if kind in NEGATIVE and qty > 0:
        raise ValueError(f"El movimiento {kind} debe restar existencia.")
