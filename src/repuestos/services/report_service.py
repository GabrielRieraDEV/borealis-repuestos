"""Reportes (RF-80 a RF-84) y foto mensual (RN-13). Datos listos para el PDF; sin Qt ni reportlab.

Permisos: el vendedor solo ve sus ventas del día y sin costos; el resto es de la dueña (UI y servicio).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import credit as credit_repo
from repuestos.db.repositories import reports as repo
from repuestos.db.repositories.inventory import ToOrderLine
from repuestos.db.repositories.reports import MethodTotal, MonthFigures, SaleRow, ValuedProduct
from repuestos.domain.money import ZERO
from repuestos.domain.users import User, require_owner
from repuestos.services import inventory_service

# ------------------------------------------------------------------ ventas del día (RF-80)


@dataclass(frozen=True, slots=True)
class SellerTotal:
    name: str
    count: int
    total_ves: Decimal
    total_usd: Decimal


@dataclass(frozen=True, slots=True)
class DailySales:
    day: date
    only_user: str | None  # nombre del vendedor si el reporte es solo de sus ventas
    count: int
    total_ves: Decimal
    total_usd: Decimal
    credit_ves: Decimal
    credit_usd: Decimal
    by_method: list[MethodTotal]
    by_seller: list[SellerTotal]
    sales: list[SaleRow]
    voided: list[SaleRow]


def daily_sales(conn: sqlite3.Connection, user: User, day: date) -> DailySales:
    """El vendedor ve solo sus ventas (sin costos: este reporte no los tiene)."""
    rows = repo.sales_between(conn, day, day, None if user.is_owner else user.id)
    ok = [s for s in rows if not s.voided]
    sellers: dict[str, list[SaleRow]] = defaultdict(list)
    for s in ok:
        sellers[s.user_name].append(s)
    return DailySales(
        day=day,
        only_user=None if user.is_owner else user.full_name,
        count=len(ok),
        total_ves=sum((s.total_ves for s in ok), ZERO),
        total_usd=sum((s.total_usd for s in ok), ZERO),
        credit_ves=sum((s.credit_ves for s in ok), ZERO),
        credit_usd=sum((s.credit_usd for s in ok), ZERO),
        by_method=repo.payments_by_method(conn, [s.id for s in ok]),
        by_seller=[
            SellerTotal(name, len(v), sum((s.total_ves for s in v), ZERO), sum((s.total_usd for s in v), ZERO))
            for name, v in sorted(sellers.items())
        ],
        sales=ok,
        voided=[s for s in rows if s.voided],
    )


# ------------------------------------------------------------------ monto vendido por período (RF-81)


@dataclass(frozen=True, slots=True)
class DayTotal:
    day: date
    count: int
    total_ves: Decimal
    base_ves: Decimal
    vat_ves: Decimal
    total_usd: Decimal


@dataclass(frozen=True, slots=True)
class PeriodSales:
    start: date
    end: date
    days: list[DayTotal]
    count: int
    total_ves: Decimal
    base_ves: Decimal
    vat_ves: Decimal
    total_usd: Decimal


def period_sales(conn: sqlite3.Connection, user: User, start: date, end: date) -> PeriodSales:
    require_owner(user, "ver el monto vendido por período")
    if end < start:
        raise ValueError("La fecha final es anterior a la inicial.")
    by_day: dict[date, list[SaleRow]] = defaultdict(list)
    for s in repo.sales_between(conn, start, end):
        if not s.voided:
            by_day[date.fromisoformat(s.created_at[:10])].append(s)
    days = [
        DayTotal(
            d,
            len(v),
            sum((s.total_ves for s in v), ZERO),
            sum((s.base_ves for s in v), ZERO),
            sum((s.vat_ves for s in v), ZERO),
            sum((s.total_usd for s in v), ZERO),
        )
        for d, v in sorted(by_day.items())
    ]
    return PeriodSales(
        start,
        end,
        days,
        sum(d.count for d in days),
        sum((d.total_ves for d in days), ZERO),
        sum((d.base_ves for d in days), ZERO),
        sum((d.vat_ves for d in days), ZERO),
        sum((d.total_usd for d in days), ZERO),
    )


# ------------------------------------------------------------------ resumen del mes (RF-82, RN-13)


def _prev(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass(frozen=True, slots=True)
class HistoryRow:
    year_month: str
    figures: MonthFigures
    inventory_close_usd: Decimal | None  # foto del cierre de ese mes (o inversión hoy si es el mes en curso)


@dataclass(frozen=True, slots=True)
class MonthSummary:
    year: int
    month: int
    figures: MonthFigures
    inventory_prev_close_usd: Decimal | None  # None = "sin dato"
    inventory_today_usd: Decimal
    receivable_usd: Decimal
    history: list[HistoryRow] = field(default_factory=list)


def _month_summary(conn: sqlite3.Connection, year: int, month: int, today: date | None = None) -> MonthSummary:
    today = today or date.today()
    py, pm = _prev(year, month)
    prev = repo.snapshot(conn, f"{py:04d}-{pm:02d}")
    inventory_today = repo.inventory_value(conn)
    history: list[HistoryRow] = []
    y, m = year, month
    for _ in range(12):
        ym = f"{y:04d}-{m:02d}"
        snap = repo.snapshot(conn, ym)
        current = (y, m) == (today.year, today.month)
        close = inventory_today if current else (snap[0] if snap else None)
        history.append(HistoryRow(ym, repo.month_figures(conn, y, m), close))
        y, m = _prev(y, m)
    return MonthSummary(
        year=year,
        month=month,
        figures=repo.month_figures(conn, year, month),
        inventory_prev_close_usd=prev[0] if prev else None,
        inventory_today_usd=inventory_today,
        receivable_usd=credit_repo.total_receivable(conn),
        history=history,
    )


def month_summary(
    conn: sqlite3.Connection, user: User, year: int, month: int, today: date | None = None
) -> MonthSummary:
    require_owner(user, "ver el resumen del mes")
    return _month_summary(conn, year, month, today)


# ------------------------------------------------------------------ inventario valorizado (RF-83)


@dataclass(frozen=True, slots=True)
class ValuedInventory:
    products: list[ValuedProduct]
    total_usd: Decimal
    without_cost: list[ValuedProduct]


def _valued_inventory(conn: sqlite3.Connection) -> ValuedInventory:
    products = repo.valued_inventory(conn)
    return ValuedInventory(
        products=products,
        total_usd=sum((p.value_usd for p in products), ZERO),
        without_cost=[p for p in products if p.cost_usd == 0],
    )


def valued_inventory(conn: sqlite3.Connection, user: User) -> ValuedInventory:
    require_owner(user, "ver el inventario valorizado")
    return _valued_inventory(conn)


# ------------------------------------------------------------------ para pedir (RF-84)


def to_order(conn: sqlite3.Connection, user: User) -> list[ToOrderLine]:
    return inventory_service.to_order(conn, user)


# ------------------------------------------------------------------ foto mensual (RN-13)


def ensure_monthly_snapshot(conn: sqlite3.Connection, today: date | None = None) -> str | None:
    """En el primer arranque de cada mes guarda la inversión en mercancía como cierre del mes anterior.

    Si el programa no se abrió el primer día, se toma igual (``taken_at`` marca la fecha real).
    No se toma si no hay movimientos anteriores al inicio del mes (base recién instalada).
    Devuelve el mes guardado o None.
    """
    today = today or date.today()
    first = today.replace(day=1)
    py, pm = _prev(today.year, today.month)
    ym = f"{py:04d}-{pm:02d}"
    if repo.snapshot(conn, ym) is not None or not repo.has_movements_before(conn, first):
        return None
    with transaction(conn):
        if repo.snapshot(conn, ym) is not None:
            return None
        repo.insert_snapshot(conn, ym, repo.inventory_value(conn))
    return ym


# Para el PDF automático de la nube (RF-92), sin usuario: lo genera el programa al cerrar caja o salir.
system_month_summary = _month_summary
system_valued_inventory = _valued_inventory
