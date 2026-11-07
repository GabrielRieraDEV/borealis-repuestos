"""Arqueo de caja (RN-11)."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from repuestos.domain.money import ZERO


def expected_cash(
    opening: Decimal,
    cash_payments: Iterable[Decimal],
    cash_in: Iterable[Decimal] = (),
    cash_out: Iterable[Decimal] = (),
) -> Decimal:
    """RN-11: esperado = apertura + Σ pagos en efectivo (vuelto negativo incluido) + entradas − salidas.

    Se calcula por moneda: con CASH_USD y movimientos en USD, o con CASH_VES y movimientos en Bs.
    Los pagos anulados no deben venir en ``cash_payments``.
    """
    return opening + sum(cash_payments, ZERO) + sum(cash_in, ZERO) - sum(cash_out, ZERO)


def cash_difference(counted: Decimal, expected: Decimal) -> Decimal:
    """RN-11: diferencia = contado − esperado (positiva = sobra, negativa = falta)."""
    return counted - expected
