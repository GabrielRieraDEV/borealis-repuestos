"""Repositorio de ventas (notas de entrega), renglones y pagos."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.domain.money import from_db, to_db
from repuestos.domain.pricing import Currency
from repuestos.domain.sale import PaymentMethod, PaymentRow


@dataclass(frozen=True, slots=True)
class SaleItem:
    id: int
    product_id: int
    product_code: str
    description: str
    qty: Decimal
    unit_price_usd: Decimal
    unit_price_ves: Decimal
    line_total_ves: Decimal
    line_total_usd: Decimal
    unit_cost_usd: Decimal | None  # None para el vendedor
    line_cost_usd: Decimal | None
    vat_rate_bp: int
    allows_fraction: bool


@dataclass(frozen=True, slots=True)
class SalePayment:
    id: int
    method: PaymentMethod
    currency: Currency
    amount: Decimal
    amount_ves: Decimal
    is_change: bool
    reference: str
    voided: bool


@dataclass(frozen=True, slots=True)
class Sale:
    id: int
    doc_type: str
    number: int
    session_id: int
    customer_id: int
    customer_name: str
    customer_id_doc: str | None
    user_id: int
    user_name: str
    rate: Decimal
    total_ves: Decimal
    base_ves: Decimal
    vat_ves: Decimal
    total_usd: Decimal
    base_usd: Decimal
    credit_usd: Decimal
    credit_ves: Decimal
    status: str
    voided_by: int | None
    voided_at: str | None
    void_reason: str | None
    created_at: str
    items: tuple[SaleItem, ...] = ()
    payments: tuple[SalePayment, ...] = ()

    @property
    def voided(self) -> bool:
        return self.status == "VOIDED"

    @property
    def doc_number(self) -> str:
        return f"{self.doc_type}-{self.number:06d}"


_SELECT = """
SELECT s.*, c.name AS customer_name, c.id_doc AS customer_id_doc, u.full_name AS user_name
FROM sales s
JOIN customers c ON c.id = s.customer_id
JOIN users u ON u.id = s.user_id
"""


def _to(r: sqlite3.Row, items: tuple[SaleItem, ...] = (), payments: tuple[SalePayment, ...] = ()) -> Sale:
    e2 = lambda col: from_db(r[col], "e2")  # noqa: E731
    return Sale(
        id=r["id"],
        doc_type=r["doc_type"],
        number=r["number"],
        session_id=r["session_id"],
        customer_id=r["customer_id"],
        customer_name=r["customer_name"],
        customer_id_doc=r["customer_id_doc"],
        user_id=r["user_id"],
        user_name=r["user_name"],
        rate=from_db(r["rate_e6"], "e6"),
        total_ves=e2("total_ves_e2"),
        base_ves=e2("base_ves_e2"),
        vat_ves=e2("vat_ves_e2"),
        total_usd=e2("total_usd_e2"),
        base_usd=e2("base_usd_e2"),
        credit_usd=e2("credit_usd_e2"),
        credit_ves=e2("credit_ves_e2"),
        status=r["status"],
        voided_by=r["voided_by"],
        voided_at=r["voided_at"],
        void_reason=r["void_reason"],
        created_at=r["created_at"],
        items=items,
        payments=payments,
    )


# ------------------------------------------------------------------ escritura


def insert_sale(
    conn: sqlite3.Connection,
    number: int,
    session_id: int,
    customer_id: int,
    user_id: int,
    rate: Decimal,
    total_ves: Decimal,
    base_ves: Decimal,
    vat_ves: Decimal,
    total_usd: Decimal,
    base_usd: Decimal,
    credit_usd: Decimal,
    credit_ves: Decimal,
) -> int:
    cur = conn.execute(
        "INSERT INTO sales (doc_type, number, session_id, customer_id, user_id, rate_e6, total_ves_e2, base_ves_e2,"
        " vat_ves_e2, total_usd_e2, base_usd_e2, credit_usd_e2, credit_ves_e2)"
        " VALUES ('NE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            number,
            session_id,
            customer_id,
            user_id,
            to_db(rate, "e6"),
            to_db(total_ves, "e2"),
            to_db(base_ves, "e2"),
            to_db(vat_ves, "e2"),
            to_db(total_usd, "e2"),
            to_db(base_usd, "e2"),
            to_db(credit_usd, "e2"),
            to_db(credit_ves, "e2"),
        ),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def insert_item(
    conn: sqlite3.Connection,
    sale_id: int,
    product_id: int,
    description: str,
    qty: Decimal,
    unit_price_usd: Decimal,
    unit_price_ves: Decimal,
    line_total_ves: Decimal,
    line_total_usd: Decimal,
    unit_cost_usd: Decimal,
    line_cost_usd: Decimal,
    vat_rate_bp: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO sale_items (sale_id, product_id, description, qty_e3, unit_price_usd_e4, unit_price_ves_e2,"
        " line_total_ves_e2, line_total_usd_e2, unit_cost_usd_e4, line_cost_usd_e2, vat_rate_bp)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sale_id,
            product_id,
            description,
            to_db(qty, "e3"),
            to_db(unit_price_usd, "e4"),
            to_db(unit_price_ves, "e2"),
            to_db(line_total_ves, "e2"),
            to_db(line_total_usd, "e2"),
            to_db(unit_cost_usd, "e4"),
            to_db(line_cost_usd, "e2"),
            vat_rate_bp,
        ),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def insert_payment(
    conn: sqlite3.Connection,
    session_id: int,
    row: PaymentRow,
    sale_id: int | None = None,
    credit_payment_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO payments (session_id, sale_id, credit_payment_id, method, currency, amount_e2, amount_ves_e2,"
        " is_change, reference) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            sale_id,
            credit_payment_id,
            row.method.value,
            row.currency.value,
            to_db(row.amount, "e2"),
            to_db(row.amount_ves, "e2"),
            int(row.is_change),
            row.reference,
        ),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def set_voided(conn: sqlite3.Connection, sale_id: int, user_id: int, reason: str) -> None:
    conn.execute(
        "UPDATE sales SET status = 'VOIDED', voided_by = ?, voided_at = datetime('now', 'localtime'),"
        " void_reason = ? WHERE id = ?",
        (user_id, reason, sale_id),
    )
    conn.execute("UPDATE payments SET voided = 1 WHERE sale_id = ?", (sale_id,))


# ------------------------------------------------------------------ lectura


def items(conn: sqlite3.Connection, sale_id: int) -> tuple[SaleItem, ...]:
    rows = conn.execute(
        "SELECT i.*, p.code, p.allows_fraction FROM sale_items i JOIN products p ON p.id = i.product_id"
        " WHERE i.sale_id = ? ORDER BY i.id",
        (sale_id,),
    )
    return tuple(
        SaleItem(
            id=r["id"],
            product_id=r["product_id"],
            product_code=r["code"],
            description=r["description"],
            qty=from_db(r["qty_e3"], "e3"),
            unit_price_usd=from_db(r["unit_price_usd_e4"], "e4"),
            unit_price_ves=from_db(r["unit_price_ves_e2"], "e2"),
            line_total_ves=from_db(r["line_total_ves_e2"], "e2"),
            line_total_usd=from_db(r["line_total_usd_e2"], "e2"),
            unit_cost_usd=from_db(r["unit_cost_usd_e4"], "e4"),
            line_cost_usd=from_db(r["line_cost_usd_e2"], "e2"),
            vat_rate_bp=r["vat_rate_bp"],
            allows_fraction=bool(r["allows_fraction"]),
        )
        for r in rows
    )


def payments(conn: sqlite3.Connection, sale_id: int) -> tuple[SalePayment, ...]:
    rows = conn.execute("SELECT * FROM payments WHERE sale_id = ? ORDER BY is_change, id", (sale_id,))
    return tuple(
        SalePayment(
            id=r["id"],
            method=PaymentMethod(r["method"]),
            currency=Currency(r["currency"]),
            amount=from_db(r["amount_e2"], "e2"),
            amount_ves=from_db(r["amount_ves_e2"], "e2"),
            is_change=bool(r["is_change"]),
            reference=r["reference"],
            voided=bool(r["voided"]),
        )
        for r in rows
    )


def get(conn: sqlite3.Connection, sale_id: int) -> Sale | None:
    r = conn.execute(_SELECT + " WHERE s.id = ?", (sale_id,)).fetchone()
    return _to(r, items(conn, sale_id), payments(conn, sale_id)) if r else None


def list_by_date(
    conn: sqlite3.Connection, day: date, user_id: int | None = None, session_id: int | None = None
) -> list[Sale]:
    sql = _SELECT + " WHERE date(s.created_at) = ?"
    params: list[object] = [day.isoformat()]
    if user_id is not None:
        sql += " AND s.user_id = ?"
        params.append(user_id)
    if session_id is not None:
        sql += " AND s.session_id = ?"
        params.append(session_id)
    return [_to(r) for r in conn.execute(sql + " ORDER BY s.number DESC", params)]
