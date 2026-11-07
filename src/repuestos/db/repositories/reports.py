"""Consultas de reportes (RF-80 a RF-84, RN-13). Solo lectura. Fechas en hora local de Caracas."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.domain.money import ZERO, from_db, hu, mul, to_db
from repuestos.domain.sale import PaymentMethod


def _ym(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


# ------------------------------------------------------------------ ventas


@dataclass(frozen=True, slots=True)
class SaleRow:
    id: int
    number: int
    created_at: str
    customer_name: str
    user_id: int
    user_name: str
    total_ves: Decimal
    total_usd: Decimal
    base_ves: Decimal
    vat_ves: Decimal
    credit_ves: Decimal
    credit_usd: Decimal
    voided: bool
    void_reason: str | None


def sales_between(conn: sqlite3.Connection, start: date, end: date, user_id: int | None = None) -> list[SaleRow]:
    sql = (
        "SELECT s.*, c.name AS customer_name, u.full_name AS user_name FROM sales s"
        " JOIN customers c ON c.id = s.customer_id JOIN users u ON u.id = s.user_id"
        " WHERE date(s.created_at) BETWEEN ? AND ?"
    )
    params: list[object] = [start.isoformat(), end.isoformat()]
    if user_id is not None:
        sql += " AND s.user_id = ?"
        params.append(user_id)
    rows = conn.execute(sql + " ORDER BY s.number", params)
    return [
        SaleRow(
            id=r["id"],
            number=r["number"],
            created_at=r["created_at"],
            customer_name=r["customer_name"],
            user_id=r["user_id"],
            user_name=r["user_name"],
            total_ves=from_db(r["total_ves_e2"], "e2"),
            total_usd=from_db(r["total_usd_e2"], "e2"),
            base_ves=from_db(r["base_ves_e2"], "e2"),
            vat_ves=from_db(r["vat_ves_e2"], "e2"),
            credit_ves=from_db(r["credit_ves_e2"], "e2"),
            credit_usd=from_db(r["credit_usd_e2"], "e2"),
            voided=r["status"] == "VOIDED",
            void_reason=r["void_reason"],
        )
        for r in rows
    ]


@dataclass(frozen=True, slots=True)
class MethodTotal:
    method: PaymentMethod
    amount: Decimal  # en su moneda, neto de vuelto
    amount_ves: Decimal
    count: int


def payments_by_method(conn: sqlite3.Connection, sale_ids: list[int]) -> list[MethodTotal]:
    if not sale_ids:
        return []
    marks = ",".join("?" * len(sale_ids))
    rows = conn.execute(
        f"SELECT method, SUM(amount_e2), SUM(amount_ves_e2), COUNT(CASE WHEN is_change = 0 THEN 1 END)"
        f" FROM payments WHERE voided = 0 AND sale_id IN ({marks}) GROUP BY method ORDER BY method",
        sale_ids,
    )
    return [MethodTotal(PaymentMethod(r[0]), from_db(r[1], "e2"), from_db(r[2], "e2"), r[3]) for r in rows]


# ------------------------------------------------------------------ resumen del mes (RN-13)


@dataclass(frozen=True, slots=True)
class MonthFigures:
    year_month: str
    purchases_usd: Decimal
    sales_count: int
    sales_usd: Decimal
    sales_ves: Decimal
    vat_usd: Decimal
    vat_ves: Decimal
    net_usd: Decimal
    net_ves: Decimal
    cost_usd: Decimal
    losses_usd: Decimal  # dañado, faltante, uso interno
    count_shortage_usd: Decimal  # ADJ_COUNT negativo ("faltantes de conteo")

    @property
    def gross_profit_usd(self) -> Decimal:
        return self.net_usd - self.cost_usd

    @property
    def result_usd(self) -> Decimal:
        return self.gross_profit_usd - self.losses_usd - self.count_shortage_usd


def _sum_e2(conn: sqlite3.Connection, sql: str, params: tuple) -> Decimal:
    return from_db(conn.execute(sql, params).fetchone()[0] or 0, "e2")


def _valued_movements(
    conn: sqlite3.Connection, ym: str, types: tuple[str, ...], negative_only: bool = False
) -> Decimal:
    """Σ HU(|cantidad| × costo del momento, 2) por movimiento (RN-13)."""
    marks = ",".join("?" * len(types))
    sql = (
        f"SELECT qty_e3, unit_cost_usd_e4 FROM inventory_movements"
        f" WHERE substr(created_at, 1, 7) = ? AND type IN ({marks})"
    )
    if negative_only:
        sql += " AND qty_e3 < 0"
    total = ZERO
    for qty_e3, cost_e4 in conn.execute(sql, (ym, *types)):
        total += hu(mul(abs(from_db(qty_e3, "e3")), from_db(cost_e4, "e4")), 2)
    return total


def month_figures(conn: sqlite3.Connection, year: int, month: int) -> MonthFigures:
    ym = _ym(year, month)
    sales = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_usd_e2), 0), COALESCE(SUM(total_ves_e2), 0),"
        " COALESCE(SUM(base_usd_e2), 0), COALESCE(SUM(base_ves_e2), 0), COALESCE(SUM(vat_ves_e2), 0)"
        " FROM sales WHERE status = 'COMPLETED' AND substr(created_at, 1, 7) = ?",
        (ym,),
    ).fetchone()
    count, t_usd, t_ves, b_usd, b_ves, v_ves = sales
    sales_usd, base_usd = from_db(t_usd, "e2"), from_db(b_usd, "e2")
    return MonthFigures(
        year_month=ym,
        purchases_usd=_sum_e2(
            conn,
            "SELECT SUM(total_usd_e2) FROM purchases WHERE status = 'COMPLETED' AND substr(purchase_date, 1, 7) = ?",
            (ym,),
        ),
        sales_count=count,
        sales_usd=sales_usd,
        sales_ves=from_db(t_ves, "e2"),
        vat_usd=sales_usd - base_usd,
        vat_ves=from_db(v_ves, "e2"),
        net_usd=base_usd,
        net_ves=from_db(b_ves, "e2"),
        cost_usd=_sum_e2(
            conn,
            "SELECT SUM(i.line_cost_usd_e2) FROM sale_items i JOIN sales s ON s.id = i.sale_id"
            " WHERE s.status = 'COMPLETED' AND substr(s.created_at, 1, 7) = ?",
            (ym,),
        ),
        losses_usd=_valued_movements(conn, ym, ("ADJ_DAMAGE", "ADJ_MISSING", "ADJ_INTERNAL_USE")),
        count_shortage_usd=_valued_movements(conn, ym, ("ADJ_COUNT",), negative_only=True),
    )


# ------------------------------------------------------------------ inventario valorizado (RF-83)


@dataclass(frozen=True, slots=True)
class ValuedProduct:
    code: str
    name: str
    category_name: str
    stock: Decimal
    cost_usd: Decimal
    value_usd: Decimal
    allows_fraction: bool
    unit: str


def valued_inventory(conn: sqlite3.Connection) -> list[ValuedProduct]:
    """RN-13: Σ HU(max(existencia, 0) × costo_promedio, 2) de productos activos."""
    rows = conn.execute(
        "SELECT p.code, p.name, COALESCE(c.name, '') AS category_name, p.stock_e3, p.cost_usd_e4,"
        " p.allows_fraction, p.unit FROM products p LEFT JOIN categories c ON c.id = p.category_id"
        " WHERE p.active = 1 ORDER BY COALESCE(c.name, '~') COLLATE NOCASE, p.name COLLATE NOCASE"
    )
    out = []
    for r in rows:
        stock = from_db(r["stock_e3"], "e3")
        cost = from_db(r["cost_usd_e4"], "e4")
        out.append(
            ValuedProduct(
                r["code"],
                r["name"],
                r["category_name"],
                stock,
                cost,
                hu(mul(max(stock, ZERO), cost), 2),
                bool(r["allows_fraction"]),
                r["unit"],
            )
        )
    return out


def inventory_value(conn: sqlite3.Connection) -> Decimal:
    return sum((p.value_usd for p in valued_inventory(conn)), ZERO)


# ------------------------------------------------------------------ foto mensual (RN-13)


def snapshot(conn: sqlite3.Connection, year_month: str) -> tuple[Decimal, str] | None:
    r = conn.execute(
        "SELECT inventory_value_usd_e2, taken_at FROM monthly_snapshots WHERE year_month = ?", (year_month,)
    ).fetchone()
    return (from_db(r[0], "e2"), r[1]) if r else None


def insert_snapshot(conn: sqlite3.Connection, year_month: str, value: Decimal) -> None:
    conn.execute(
        "INSERT INTO monthly_snapshots (year_month, inventory_value_usd_e2) VALUES (?, ?)",
        (year_month, to_db(value, "e2")),
    )


def has_movements_before(conn: sqlite3.Connection, day: date) -> bool:
    return (
        conn.execute("SELECT 1 FROM inventory_movements WHERE created_at < ? LIMIT 1", (day.isoformat(),)).fetchone()
        is not None
    )
