"""Fórmulas de precio, venta, pago, fiado y costo (docs/02-reglas-de-negocio.md).

Funciones puras con Decimal. Cada una cita la regla que implementa.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from repuestos.domain.money import ZERO, div, hu, mul, percent_factor, techo

DEFAULT_VAT_BP = 1600


class Currency(StrEnum):
    VES = "VES"
    USD = "USD"


# ------------------------------------------------------------------ RN-03


def unit_price_ves(price_usd: Decimal, rate: Decimal, multiple: Decimal) -> Decimal:
    """RN-03: precio_bs = TECHO(price_usd × tasa, múltiplo), con 2 decimales."""
    if price_usd < 0:
        raise ValueError("el precio no puede ser negativo")
    if rate <= 0:
        raise ValueError("la tasa debe ser mayor que cero")
    return hu(techo(mul(price_usd, rate), multiple), 2)


# ------------------------------------------------------------------ RN-04


@dataclass(frozen=True, slots=True)
class LineTotals:
    total_ves: Decimal
    total_usd: Decimal
    cost_usd: Decimal


def line_totals(qty: Decimal, unit_price_ves_: Decimal, price_usd: Decimal, unit_cost_usd: Decimal) -> LineTotals:
    """RN-04: totales del renglón (Bs, referencia USD y costo), cada uno HU a 2 decimales."""
    if qty <= 0:
        raise ValueError("la cantidad debe ser mayor que cero")
    return LineTotals(
        total_ves=hu(mul(qty, unit_price_ves_), 2),
        total_usd=hu(mul(qty, price_usd), 2),
        cost_usd=hu(mul(qty, unit_cost_usd), 2),
    )


def check_quantity(qty: Decimal, allows_fraction: bool) -> None:
    """RN-04: decimales solo si el producto permite fracción, y como máximo 3."""
    if qty <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    if not allows_fraction and qty != qty.to_integral_value():
        raise ValueError("Este producto se vende por unidades completas.")
    if qty != hu(qty, 3):
        raise ValueError("La cantidad admite como máximo 3 decimales.")


# ------------------------------------------------------------------ RN-05


@dataclass(frozen=True, slots=True)
class DocumentTotals:
    total: Decimal
    base: Decimal
    vat: Decimal


def document_totals(line_totals_: Iterable[Decimal], vat_rate_bp: int = DEFAULT_VAT_BP) -> DocumentTotals:
    """RN-05: total = Σ renglones; base = HU(total / 1,16, 2); IVA = total − base.

    Se aplica igual para Bs y para la referencia en USD.
    """
    total = sum(line_totals_, ZERO)
    base = hu(div(total, percent_factor(vat_rate_bp)), 2)
    return DocumentTotals(total=total, base=base, vat=total - base)


# ------------------------------------------------------------------ RN-06


def ves_equivalent(amount: Decimal, currency: Currency, rate: Decimal) -> Decimal:
    """RN-06: equivalente en Bs de un pago. VES tal cual; USD = HU(monto × tasa, 2)."""
    if currency is Currency.VES:
        return amount
    return hu(mul(amount, rate), 2)


def amount_due_ves(total_ves: Decimal, paid_ves: Decimal) -> Decimal:
    """RN-06: falta_bs = total_bs − pagado_bs (negativo = hay vuelto)."""
    return total_ves - paid_ves


def usd_reference(amount_ves: Decimal, rate: Decimal) -> Decimal:
    """RN-06: referencia en USD de un monto en Bs = HU(monto / tasa, 2)."""
    return hu(div(amount_ves, rate), 2)


@dataclass(frozen=True, slots=True)
class Change:
    total_ves: Decimal  # vuelto total en Bs
    usd: Decimal  # lo que se entrega en USD
    rest_ves: Decimal  # lo que se entrega en Bs


def compute_change(total_ves: Decimal, paid_ves: Decimal, change_usd: Decimal, rate: Decimal) -> Change:
    """RN-06: vuelto_bs = pagado − total; resto_bs = vuelto_bs − HU(vuelto_usd × tasa, 2).

    Falla si el resto da negativo (se estaría dando de más).
    """
    change_ves = paid_ves - total_ves
    if change_ves < 0:
        raise ValueError("Todavía falta dinero: no hay vuelto.")
    if change_usd < 0:
        raise ValueError("El vuelto en USD no puede ser negativo.")
    rest = change_ves - hu(mul(change_usd, rate), 2)
    if rest < 0:
        raise ValueError("El vuelto en USD es mayor que el vuelto que corresponde.")
    return Change(total_ves=change_ves, usd=change_usd, rest_ves=rest)


# ------------------------------------------------------------------ RN-07


def credit_debt_usd(credit_ves: Decimal, sale_rate: Decimal) -> Decimal:
    """RN-07: deuda_usd = HU((total_bs − pagado_bs) / tasa_de_la_venta, 2)."""
    if credit_ves <= 0:
        raise ValueError("el monto fiado debe ser mayor que cero")
    return hu(div(credit_ves, sale_rate), 2)


def credit_payment_usd(amount: Decimal, currency: Currency, current_rate: Decimal) -> Decimal:
    """RN-07: abono_usd = monto si es USD; HU(monto_bs / tasa_vigente, 2) si es VES."""
    if amount <= 0:
        raise ValueError("El abono debe ser mayor que cero.")
    if currency is Currency.USD:
        return amount
    return hu(div(amount, current_rate), 2)


# ------------------------------------------------------------------ RN-08


def weighted_average_cost(
    stock_before: Decimal, cost_before: Decimal, qty: Decimal, purchase_cost: Decimal
) -> Decimal:
    """RN-08: costo promedio ponderado tras un renglón de compra (4 decimales).

    Si la existencia anterior es <= 0, el costo nuevo es el de la compra.
    """
    if qty <= 0:
        raise ValueError("la cantidad comprada debe ser mayor que cero")
    if purchase_cost < 0:
        raise ValueError("el costo no puede ser negativo")
    if stock_before <= 0:
        return hu(purchase_cost, 4)
    numerator = mul(stock_before, cost_before) + mul(qty, purchase_cost)
    return hu(div(numerator, stock_before + qty), 4)


@dataclass(frozen=True, slots=True)
class PackPurchase:
    qty: Decimal
    unit_cost: Decimal


def pack_purchase(packs: Decimal, units_per_pack: Decimal, pack_cost: Decimal) -> PackPurchase:
    """RN-08: compra por empaque. cantidad = empaques × unidades; costo = HU(costo_empaque / unidades, 4)."""
    if packs <= 0 or units_per_pack <= 0:
        raise ValueError("empaques y unidades por empaque deben ser mayores que cero")
    return PackPurchase(qty=mul(packs, units_per_pack), unit_cost=hu(div(pack_cost, units_per_pack), 4))
