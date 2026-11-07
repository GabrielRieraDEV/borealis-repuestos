"""Fiado (RF-70 a RF-73, RN-07, RN-14): abonos con reparto FIFO, anulación de abonos, estado de cuenta y deudores.

Abono = una transacción: doc_sequences('AB'), credit_payments, credit_allocations, receivables, payments.
El abono entra a la caja abierta como cualquier pago (cuenta para el arqueo si es efectivo, RN-11).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import credit as repo
from repuestos.db.repositories import customers as customers_repo
from repuestos.db.repositories import sales as sales_repo
from repuestos.db.repositories import sequences
from repuestos.db.repositories.credit import CreditPayment, DebtorRow, Receivable
from repuestos.db.repositories.customers import Customer
from repuestos.db.repositories.sales import SalePayment
from repuestos.domain.credit import allocate_fifo, is_overdue
from repuestos.domain.money import ZERO, hu
from repuestos.domain.pricing import credit_payment_usd, ves_equivalent
from repuestos.domain.sale import METHOD_CURRENCY, PaymentMethod, PaymentRow
from repuestos.domain.users import User, require_owner
from repuestos.services import cash_service, rate_service, settings_service
from repuestos.services.audit_service import audit

# ------------------------------------------------------------------ configuración del cliente (RF-70)


def set_customer_credit(
    conn: sqlite3.Connection,
    owner: User,
    customer_id: int,
    enabled: bool,
    limit_usd: Decimal | None = None,
    days: int | None = None,
) -> Customer:
    """La dueña habilita el fiado, con límite opcional en USD y plazo (si no, el de la configuración)."""
    require_owner(owner, "habilitar fiado")
    if limit_usd is not None and (limit_usd < 0 or limit_usd != hu(limit_usd, 2)):
        raise ValueError("El límite debe ser un monto en USD con 2 decimales como máximo.")
    if days is not None and days <= 0:
        raise ValueError("El plazo debe ser de al menos 1 día.")
    with transaction(conn):
        customer = customers_repo.get(conn, customer_id)
        if customer is None:
            raise LookupError("El cliente no existe.")
        if customer.is_final_consumer:
            raise ValueError("«Consumidor final» nunca puede tener fiado.")
        customers_repo.update_credit(conn, customer_id, enabled, limit_usd, days)
        audit(
            conn,
            owner.id,
            "CUSTOMER_CREDIT_CHANGED",
            "customer",
            customer_id,
            {
                "antes": {
                    "habilitado": customer.credit_enabled,
                    "limite_usd": customer.credit_limit_usd,
                    "dias": customer.credit_days,
                },
                "despues": {"habilitado": enabled, "limite_usd": limit_usd, "dias": days},
            },
        )
    updated = customers_repo.get(conn, customer_id)
    assert updated is not None
    return updated


def update_customer_info(conn: sqlite3.Connection, owner: User, customer_id: int, name: str, phone: str) -> None:
    require_owner(owner, "editar clientes")
    name = " ".join(name.split())
    if not name:
        raise ValueError("Escriba el nombre del cliente.")
    with transaction(conn):
        customer = customers_repo.get(conn, customer_id)
        if customer is None or customer.is_final_consumer:
            raise ValueError("Ese cliente no se puede editar.")
        customers_repo.update_info(conn, customer_id, name, phone.strip())
        audit(conn, owner.id, "CUSTOMER_UPDATED", "customer", customer_id, {"nombre": name})


def list_customers(conn: sqlite3.Connection, text: str = "") -> list[Customer]:
    return customers_repo.list_all(conn, text.strip())


# ------------------------------------------------------------------ abonos (RF-72)


@dataclass(frozen=True, slots=True)
class PaymentPreview:
    amount_usd: Decimal
    balance_before: Decimal
    balance_after: Decimal


def preview_payment(
    conn: sqlite3.Connection, customer_id: int, method: PaymentMethod, amount: Decimal, today: date | None = None
) -> PaymentPreview:
    """Cuánto abona en USD con la tasa vigente y cómo queda el saldo (para mostrar antes de guardar)."""
    rate = rate_service.require_rate(conn, today).rate
    usd = credit_payment_usd(amount, METHOD_CURRENCY[method], rate)
    balance = repo.customer_balance(conn, customer_id)
    return PaymentPreview(usd, balance, balance - usd)


def register_payment(
    conn: sqlite3.Connection,
    user: User,
    customer_id: int,
    method: PaymentMethod,
    amount: Decimal,
    reference: str = "",
    today: date | None = None,
) -> CreditPayment:
    """Abono en cualquier forma de pago menos fiado, con la tasa vigente; FIFO; entra a la caja abierta."""
    if method is PaymentMethod.CREDIT:
        raise ValueError("Un abono no se puede pagar con fiado.")
    if amount <= 0:
        raise ValueError("El abono debe ser mayor que cero.")
    if amount != hu(amount, 2):
        raise ValueError("El monto admite como máximo 2 decimales.")
    with transaction(conn):
        session = cash_service.require_open_session(conn)
        rate = rate_service.require_rate(conn, today).rate
        if method is PaymentMethod.USDT and not settings_service.load(conn).payment_usdt_enabled:
            raise ValueError("Binance USDT no está activado como forma de pago.")
        customer = customers_repo.get(conn, customer_id)
        if customer is None:
            raise LookupError("El cliente no existe.")
        currency = METHOD_CURRENCY[method]
        amount_usd = credit_payment_usd(amount, currency, rate)
        debts = repo.open_receivables(conn, customer_id)
        if not debts:
            raise ValueError(f"{customer.name} no tiene deudas pendientes.")
        allocations = allocate_fifo(amount_usd, [(d.id, d.balance_usd) for d in debts])

        number = sequences.take_next(conn, "AB")
        payment_id = repo.insert_credit_payment(conn, number, customer_id, session.id, user.id, rate, amount_usd)
        balances = {d.id: d.balance_usd for d in debts}
        for a in allocations:
            repo.insert_allocation(conn, payment_id, a.receivable_id, a.amount)
            repo.set_balance(conn, a.receivable_id, balances[a.receivable_id] - a.amount)
        row = PaymentRow(method, currency, amount, ves_equivalent(amount, currency, rate), False, reference.strip())
        sales_repo.insert_payment(conn, session.id, row, credit_payment_id=payment_id)
    created = repo.get_credit_payment(conn, payment_id)
    assert created is not None
    return created


def void_payment(conn: sqlite3.Connection, user: User, credit_payment_id: int, reason: str) -> None:
    """RN-14: la dueña, mientras la caja del abono siga abierta. Revierte el reparto y anula el pago."""
    require_owner(user, "anular abonos")
    reason = " ".join(reason.split())
    if not reason:
        raise ValueError("Escriba el motivo de la anulación.")
    with transaction(conn):
        payment = repo.get_credit_payment(conn, credit_payment_id)
        if payment is None:
            raise LookupError("El abono no existe.")
        if payment.voided:
            raise ValueError(f"El abono {payment.doc_number} ya está anulado.")
        session = cash_service.current_session(conn)
        if session is None or session.id != payment.session_id:
            raise ValueError("Ese abono es de una caja ya cerrada: no se puede anular.")
        for a in payment.allocations:
            receivable = repo.get_receivable(conn, a.receivable_id)
            assert receivable is not None and receivable.status != "VOIDED"  # una venta con abonos no se anula
            repo.set_balance(conn, a.receivable_id, receivable.balance_usd + a.amount_usd)
        repo.set_credit_payment_voided(conn, credit_payment_id, user.id, reason)
        audit(
            conn,
            user.id,
            "CREDIT_PAYMENT_VOID",
            "credit_payment",
            credit_payment_id,
            {"abono": payment.doc_number, "usd": payment.amount_usd, "motivo": reason},
        )


def payment_detail(conn: sqlite3.Connection, credit_payment_id: int) -> tuple[CreditPayment, tuple[SalePayment, ...]]:
    payment = repo.get_credit_payment(conn, credit_payment_id)
    if payment is None:
        raise LookupError("El abono no existe.")
    return payment, repo.payments_of_credit_payment(conn, credit_payment_id)


# ------------------------------------------------------------------ estado de cuenta y deudores (RF-73)


@dataclass(frozen=True, slots=True)
class DebtLine:
    receivable: Receivable
    overdue: bool


@dataclass(frozen=True, slots=True)
class Statement:
    customer: Customer
    balance_usd: Decimal
    overdue_usd: Decimal
    debts: list[DebtLine]
    payments: list[CreditPayment]


def statement(conn: sqlite3.Connection, customer_id: int, today: date | None = None) -> Statement:
    today = today or date.today()
    customer = customers_repo.get(conn, customer_id)
    if customer is None:
        raise LookupError("El cliente no existe.")
    debts = [
        DebtLine(r, r.status == "OPEN" and is_overdue(r.due_date, r.balance_usd, today))
        for r in repo.receivables_of(conn, customer_id)
    ]
    open_debts = [d for d in debts if d.receivable.status == "OPEN"]
    return Statement(
        customer=customer,
        balance_usd=sum((d.receivable.balance_usd for d in open_debts), ZERO),
        overdue_usd=sum((d.receivable.balance_usd for d in open_debts if d.overdue), ZERO),
        debts=debts,
        payments=repo.credit_payments_of(conn, customer_id),
    )


def debtors(conn: sqlite3.Connection, today: date | None = None) -> list[DebtorRow]:
    return repo.debtors(conn, today or date.today())


def total_receivable(conn: sqlite3.Connection) -> Decimal:
    return repo.total_receivable(conn)


def customer_balance(conn: sqlite3.Connection, customer_id: int) -> Decimal:
    return repo.customer_balance(conn, customer_id)
