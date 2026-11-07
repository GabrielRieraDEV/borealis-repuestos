"""Repositorio de fiado: deudas (receivables), abonos (credit_payments) y su reparto (credit_allocations)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.db.repositories.sales import SalePayment
from repuestos.domain.money import from_db, to_db
from repuestos.domain.pricing import Currency
from repuestos.domain.sale import PaymentMethod


@dataclass(frozen=True, slots=True)
class Receivable:
    id: int
    sale_id: int
    sale_number: int
    customer_id: int
    amount_usd: Decimal
    balance_usd: Decimal
    due_date: date
    status: str
    created_at: str

    @property
    def doc_number(self) -> str:
        return f"NE-{self.sale_number:06d}"


@dataclass(frozen=True, slots=True)
class CreditAllocationLine:
    receivable_id: int
    sale_number: int
    amount_usd: Decimal


@dataclass(frozen=True, slots=True)
class CreditPayment:
    id: int
    number: int
    customer_id: int
    session_id: int
    user_id: int
    user_name: str
    rate: Decimal
    amount_usd: Decimal
    status: str
    void_reason: str | None
    created_at: str
    allocations: tuple[CreditAllocationLine, ...] = ()

    @property
    def doc_number(self) -> str:
        return f"AB-{self.number:06d}"

    @property
    def voided(self) -> bool:
        return self.status == "VOIDED"


def _receivable(r: sqlite3.Row) -> Receivable:
    return Receivable(
        id=r["id"],
        sale_id=r["sale_id"],
        sale_number=r["sale_number"],
        customer_id=r["customer_id"],
        amount_usd=from_db(r["amount_usd_e2"], "e2"),
        balance_usd=from_db(r["balance_usd_e2"], "e2"),
        due_date=date.fromisoformat(r["due_date"]),
        status=r["status"],
        created_at=r["created_at"],
    )


_RECEIVABLES = "SELECT r.*, s.number AS sale_number FROM receivables r JOIN sales s ON s.id = r.sale_id"


# ------------------------------------------------------------------ deudas


def insert_receivable(conn: sqlite3.Connection, sale_id: int, customer_id: int, amount_usd: Decimal, due: date) -> int:
    cur = conn.execute(
        "INSERT INTO receivables (sale_id, customer_id, amount_usd_e2, balance_usd_e2, due_date)"
        " VALUES (?, ?, ?, ?, ?)",
        (sale_id, customer_id, to_db(amount_usd, "e2"), to_db(amount_usd, "e2"), due.isoformat()),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def open_receivables(conn: sqlite3.Connection, customer_id: int) -> list[Receivable]:
    """Deudas con saldo, de la más vieja a la más nueva (orden FIFO)."""
    rows = conn.execute(
        _RECEIVABLES + " WHERE r.customer_id = ? AND r.status = 'OPEN' ORDER BY r.created_at, r.id", (customer_id,)
    )
    return [_receivable(r) for r in rows]


def receivables_of(conn: sqlite3.Connection, customer_id: int) -> list[Receivable]:
    rows = conn.execute(_RECEIVABLES + " WHERE r.customer_id = ? ORDER BY r.created_at DESC, r.id DESC", (customer_id,))
    return [_receivable(r) for r in rows]


def get_receivable(conn: sqlite3.Connection, receivable_id: int) -> Receivable | None:
    r = conn.execute(_RECEIVABLES + " WHERE r.id = ?", (receivable_id,)).fetchone()
    return _receivable(r) if r else None


def receivable_of_sale(conn: sqlite3.Connection, sale_id: int) -> Receivable | None:
    r = conn.execute(_RECEIVABLES + " WHERE r.sale_id = ?", (sale_id,)).fetchone()
    return _receivable(r) if r else None


def customer_balance(conn: sqlite3.Connection, customer_id: int) -> Decimal:
    r = conn.execute(
        "SELECT COALESCE(SUM(balance_usd_e2), 0) FROM receivables WHERE customer_id = ? AND status = 'OPEN'",
        (customer_id,),
    ).fetchone()
    return from_db(r[0], "e2")


def set_balance(conn: sqlite3.Connection, receivable_id: int, balance: Decimal) -> None:
    conn.execute(
        "UPDATE receivables SET balance_usd_e2 = ?, status = CASE WHEN ? = 0 THEN 'PAID' ELSE 'OPEN' END WHERE id = ?",
        (to_db(balance, "e2"), to_db(balance, "e2"), receivable_id),
    )


def void_receivable(conn: sqlite3.Connection, receivable_id: int) -> None:
    conn.execute("UPDATE receivables SET status = 'VOIDED' WHERE id = ?", (receivable_id,))


def active_allocations_count(conn: sqlite3.Connection, receivable_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM credit_allocations a JOIN credit_payments p ON p.id = a.credit_payment_id"
        " WHERE a.receivable_id = ? AND p.status = 'COMPLETED'",
        (receivable_id,),
    ).fetchone()[0]


@dataclass(frozen=True, slots=True)
class DebtorRow:
    customer_id: int
    name: str
    id_doc: str | None
    phone: str
    balance_usd: Decimal
    overdue_usd: Decimal
    oldest_due: date
    open_count: int


def debtors(conn: sqlite3.Connection, today: date) -> list[DebtorRow]:
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.id_doc, c.phone,
               SUM(r.balance_usd_e2) AS balance,
               SUM(CASE WHEN r.due_date < ? THEN r.balance_usd_e2 ELSE 0 END) AS overdue,
               MIN(r.due_date) AS oldest_due, COUNT(*) AS n
        FROM receivables r JOIN customers c ON c.id = r.customer_id
        WHERE r.status = 'OPEN' AND r.balance_usd_e2 > 0
        GROUP BY c.id
        ORDER BY overdue DESC, balance DESC, c.name COLLATE NOCASE
        """,
        (today.isoformat(),),
    )
    return [
        DebtorRow(
            customer_id=r["id"],
            name=r["name"],
            id_doc=r["id_doc"],
            phone=r["phone"],
            balance_usd=from_db(r["balance"], "e2"),
            overdue_usd=from_db(r["overdue"], "e2"),
            oldest_due=date.fromisoformat(r["oldest_due"]),
            open_count=r["n"],
        )
        for r in rows
    ]


def total_receivable(conn: sqlite3.Connection) -> Decimal:
    r = conn.execute("SELECT COALESCE(SUM(balance_usd_e2), 0) FROM receivables WHERE status = 'OPEN'").fetchone()
    return from_db(r[0], "e2")


# ------------------------------------------------------------------ abonos


def insert_credit_payment(
    conn: sqlite3.Connection,
    number: int,
    customer_id: int,
    session_id: int,
    user_id: int,
    rate: Decimal,
    amount_usd: Decimal,
) -> int:
    cur = conn.execute(
        "INSERT INTO credit_payments (number, customer_id, session_id, user_id, rate_e6, amount_usd_e2)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (number, customer_id, session_id, user_id, to_db(rate, "e6"), to_db(amount_usd, "e2")),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def insert_allocation(conn: sqlite3.Connection, credit_payment_id: int, receivable_id: int, amount: Decimal) -> None:
    conn.execute(
        "INSERT INTO credit_allocations (credit_payment_id, receivable_id, amount_usd_e2) VALUES (?, ?, ?)",
        (credit_payment_id, receivable_id, to_db(amount, "e2")),
    )


def allocations(conn: sqlite3.Connection, credit_payment_id: int) -> tuple[CreditAllocationLine, ...]:
    rows = conn.execute(
        "SELECT a.receivable_id, s.number, a.amount_usd_e2 FROM credit_allocations a"
        " JOIN receivables r ON r.id = a.receivable_id JOIN sales s ON s.id = r.sale_id"
        " WHERE a.credit_payment_id = ? ORDER BY a.id",
        (credit_payment_id,),
    )
    return tuple(CreditAllocationLine(r[0], r[1], from_db(r[2], "e2")) for r in rows)


_PAYMENTS = "SELECT p.*, u.full_name AS user_name FROM credit_payments p JOIN users u ON u.id = p.user_id"


def _payment(conn: sqlite3.Connection, r: sqlite3.Row) -> CreditPayment:
    return CreditPayment(
        id=r["id"],
        number=r["number"],
        customer_id=r["customer_id"],
        session_id=r["session_id"],
        user_id=r["user_id"],
        user_name=r["user_name"],
        rate=from_db(r["rate_e6"], "e6"),
        amount_usd=from_db(r["amount_usd_e2"], "e2"),
        status=r["status"],
        void_reason=r["void_reason"],
        created_at=r["created_at"],
        allocations=allocations(conn, r["id"]),
    )


def get_credit_payment(conn: sqlite3.Connection, credit_payment_id: int) -> CreditPayment | None:
    r = conn.execute(_PAYMENTS + " WHERE p.id = ?", (credit_payment_id,)).fetchone()
    return _payment(conn, r) if r else None


def credit_payments_of(conn: sqlite3.Connection, customer_id: int) -> list[CreditPayment]:
    rows = conn.execute(_PAYMENTS + " WHERE p.customer_id = ? ORDER BY p.id DESC", (customer_id,)).fetchall()
    return [_payment(conn, r) for r in rows]


def set_credit_payment_voided(conn: sqlite3.Connection, credit_payment_id: int, user_id: int, reason: str) -> None:
    conn.execute(
        "UPDATE credit_payments SET status = 'VOIDED', voided_by = ?, voided_at = datetime('now', 'localtime'),"
        " void_reason = ? WHERE id = ?",
        (user_id, reason, credit_payment_id),
    )
    conn.execute("UPDATE payments SET voided = 1 WHERE credit_payment_id = ?", (credit_payment_id,))


def payments_of_credit_payment(conn: sqlite3.Connection, credit_payment_id: int) -> tuple[SalePayment, ...]:
    rows = conn.execute("SELECT * FROM payments WHERE credit_payment_id = ? ORDER BY id", (credit_payment_id,))
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
