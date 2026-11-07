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


class AdjustmentKind(StrEnum):
    """Ajustes manuales de la dueña (RF-41). El conteo físico (RF-42) usa ADJ_COUNT aparte."""

    DAMAGE = "DAMAGE"
    MISSING = "MISSING"
    INTERNAL_USE = "INTERNAL_USE"
    CORRECTION_IN = "CORRECTION_IN"


ADJUSTMENT_MOVEMENT = {
    AdjustmentKind.DAMAGE: MovementType.ADJ_DAMAGE,
    AdjustmentKind.MISSING: MovementType.ADJ_MISSING,
    AdjustmentKind.INTERNAL_USE: MovementType.ADJ_INTERNAL_USE,
    AdjustmentKind.CORRECTION_IN: MovementType.ADJ_CORRECTION_IN,
}

ADJUSTMENT_LABELS = {
    AdjustmentKind.DAMAGE: "Dañado",
    AdjustmentKind.MISSING: "Faltante",
    AdjustmentKind.INTERNAL_USE: "Uso interno",
    AdjustmentKind.CORRECTION_IN: "Entrada por corrección",
}


def adjustment_qty(kind: AdjustmentKind, qty: Decimal) -> Decimal:
    """La usuaria escribe una cantidad positiva; el signo lo pone el tipo (RN-09)."""
    if qty <= 0:
        raise ValueError("La cantidad del ajuste debe ser mayor que cero.")
    return qty if kind is AdjustmentKind.CORRECTION_IN else -qty


def count_difference(counted: Decimal, system_stock: Decimal) -> Decimal:
    """RN-09: diferencia = contado − existencia del sistema."""
    if counted < 0:
        raise ValueError("Lo contado no puede ser negativo.")
    return counted - system_stock
