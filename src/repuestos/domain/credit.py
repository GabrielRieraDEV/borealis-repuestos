"""Fiado (RN-07): deuda en USD, vencimiento, límite y reparto FIFO de los abonos."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from repuestos.domain.money import ZERO
from repuestos.formatting import format_usd


def due_date(sale_date: date, days: int) -> date:
    """Vence en fecha_venta + plazo_días."""
    if days <= 0:
        raise ValueError("El plazo de fiado debe ser de al menos 1 día.")
    return sale_date + timedelta(days=days)


def is_overdue(due: date, balance: Decimal, today: date) -> bool:
    """Vencida si hoy es posterior al vencimiento y el saldo es > 0."""
    return today > due and balance > 0


def within_limit(limit: Decimal | None, current_balance: Decimal, new_debt: Decimal) -> bool:
    """Límite: saldo_actual + deuda_nueva <= límite. Sin límite, siempre se puede."""
    return limit is None or current_balance + new_debt <= limit


@dataclass(frozen=True, slots=True)
class Allocation:
    receivable_id: int
    amount: Decimal


def allocate_fifo(amount: Decimal, open_debts: Iterable[tuple[int, Decimal]]) -> list[Allocation]:
    """Reparte el abono a la deuda más vieja primero. ``open_debts`` ya viene ordenada de la más vieja a la nueva.

    No se permite abonar más que el saldo total.
    """
    if amount <= 0:
        raise ValueError("El abono debe ser mayor que cero.")
    debts = list(open_debts)
    total = sum((balance for _, balance in debts), ZERO)
    if amount > total:
        raise ValueError(f"El abono es mayor que la deuda: el saldo total es {format_usd(total)}.")
    out: list[Allocation] = []
    remaining = amount
    for receivable_id, balance in debts:
        if remaining == 0:
            break
        take = min(remaining, balance)
        if take > 0:
            out.append(Allocation(receivable_id, take))
            remaining -= take
    return out
