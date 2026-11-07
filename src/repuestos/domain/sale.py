"""Venta y cobro: formas de pago, resumen de lo pagado, lo que falta y el vuelto (RN-04 a RN-06)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from repuestos.domain.money import ZERO, hu
from repuestos.domain.pricing import Currency, compute_change, usd_reference, ves_equivalent


class PaymentMethod(StrEnum):
    CASH_VES = "CASH_VES"
    CASH_USD = "CASH_USD"
    POS = "POS"
    MOBILE = "MOBILE"
    USDT = "USDT"
    CREDIT = "CREDIT"  # fiado: no es una fila de pago (Fase 4)


METHOD_CURRENCY = {
    PaymentMethod.CASH_VES: Currency.VES,
    PaymentMethod.CASH_USD: Currency.USD,
    PaymentMethod.POS: Currency.VES,
    PaymentMethod.MOBILE: Currency.VES,
    PaymentMethod.USDT: Currency.USD,
    PaymentMethod.CREDIT: Currency.USD,
}

METHOD_LABELS = {
    PaymentMethod.CASH_VES: "Efectivo Bs",
    PaymentMethod.CASH_USD: "Efectivo USD",
    PaymentMethod.POS: "Punto de venta",
    PaymentMethod.MOBILE: "Pago móvil",
    PaymentMethod.USDT: "Binance USDT",
    PaymentMethod.CREDIT: "Fiado",
}

#: Cuentan para el arqueo de caja (RN-11).
CASH_METHODS = {PaymentMethod.CASH_VES, PaymentMethod.CASH_USD}
#: Se listan al cerrar caja para verificar contra el banco (RN-11).
NON_CASH_METHODS = (PaymentMethod.POS, PaymentMethod.MOBILE, PaymentMethod.USDT)


@dataclass(frozen=True, slots=True)
class PaymentInput:
    method: PaymentMethod
    amount: Decimal  # en la moneda de la forma de pago, positivo
    reference: str = ""

    @property
    def currency(self) -> Currency:
        return METHOD_CURRENCY[self.method]


def check_payment(p: PaymentInput) -> None:
    if p.method is PaymentMethod.CREDIT:
        raise ValueError("El fiado no se registra como pago.")
    if p.amount <= 0:
        raise ValueError("Cada pago debe ser mayor que cero.")
    if p.amount != hu(p.amount, 2):
        raise ValueError("Los montos admiten como máximo 2 decimales.")


@dataclass(frozen=True, slots=True)
class PaymentSummary:
    total_ves: Decimal
    paid_ves: Decimal
    due_ves: Decimal  # lo que falta (0 si ya se pagó todo)
    due_usd_ref: Decimal  # referencia en USD de lo que falta
    change_ves: Decimal  # vuelto total en Bs (0 si no hay)

    @property
    def complete(self) -> bool:
        return self.paid_ves >= self.total_ves


def payment_summary(total_ves: Decimal, payments: Iterable[PaymentInput], rate: Decimal) -> PaymentSummary:
    """RN-06: pagado_bs = Σ equivalente_bs; falta_bs = total − pagado; vuelto = pagado − total."""
    paid = sum((ves_equivalent(p.amount, p.currency, rate) for p in payments), ZERO)
    due = max(total_ves - paid, ZERO)
    return PaymentSummary(
        total_ves=total_ves,
        paid_ves=paid,
        due_ves=due,
        due_usd_ref=usd_reference(due, rate),
        change_ves=max(paid - total_ves, ZERO),
    )


@dataclass(frozen=True, slots=True)
class PaymentRow:
    """Una fila de ``payments`` ya calculada (vuelto con monto negativo)."""

    method: PaymentMethod
    currency: Currency
    amount: Decimal
    amount_ves: Decimal
    is_change: bool
    reference: str = ""


def payment_rows(
    total_ves: Decimal, payments: list[PaymentInput], rate: Decimal, change_usd: Decimal = ZERO
) -> list[PaymentRow]:
    """Filas a guardar: pagos y, si hay vuelto, filas negativas en USD y/o Bs (RN-06).

    Garantiza la invariante 3: Σ amount_ves (incluido el vuelto) = total_ves.
    """
    for p in payments:
        check_payment(p)
    summary = payment_summary(total_ves, payments, rate)
    if not summary.complete:
        raise ValueError("Todavía falta dinero por cobrar.")
    rows = [
        PaymentRow(p.method, p.currency, p.amount, ves_equivalent(p.amount, p.currency, rate), False, p.reference)
        for p in payments
    ]
    if change_usd != hu(change_usd, 2):
        raise ValueError("El vuelto en USD admite como máximo 2 decimales.")
    if summary.change_ves > 0 or change_usd > 0:
        change = compute_change(total_ves, summary.paid_ves, change_usd, rate)
        if change.usd > 0:
            usd_ves = ves_equivalent(change.usd, Currency.USD, rate)
            rows.append(PaymentRow(PaymentMethod.CASH_USD, Currency.USD, -change.usd, -usd_ves, True))
        if change.rest_ves > 0:
            rows.append(PaymentRow(PaymentMethod.CASH_VES, Currency.VES, -change.rest_ves, -change.rest_ves, True))
    assert sum((r.amount_ves for r in rows), ZERO) == total_ves
    return rows
