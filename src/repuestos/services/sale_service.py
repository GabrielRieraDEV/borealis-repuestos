"""Ventas (RF-50 a RF-56, RN-03 a RN-06, RN-09, RN-12, RN-14).

Cobrar = una transacción: doc_sequences('NE'), sales, sale_items (copias de precio, costo y descripción), payments
(con el vuelto), inventory_movements(SALE), products.stock_e3 y audit_log si se vendió sin existencia.
La impresión ocurre después del COMMIT y su falla nunca revierte la venta.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import credit as credit_repo
from repuestos.db.repositories import customers as customers_repo
from repuestos.db.repositories import products as products_repo
from repuestos.db.repositories import sales as repo
from repuestos.db.repositories import sequences
from repuestos.db.repositories import users as users_repo
from repuestos.db.repositories.sales import Sale
from repuestos.domain.credit import due_date, within_limit
from repuestos.domain.inventory import MovementType
from repuestos.domain.money import ZERO
from repuestos.domain.pricing import (
    DocumentTotals,
    check_quantity,
    credit_debt_usd,
    document_totals,
    line_totals,
    unit_price_ves,
)
from repuestos.domain.products import Product
from repuestos.domain.sale import PaymentInput, PaymentMethod, check_payment, credit_rows, payment_rows
from repuestos.domain.users import User
from repuestos.formatting import format_usd
from repuestos.services import cash_service, rate_service, settings_service
from repuestos.services.audit_service import audit
from repuestos.services.stock import apply_movement


class RateChangedError(ValueError):
    """La tasa vigente cambió mientras se armaba la venta: hay que recalcular los precios."""

    def __init__(self, new_rate: Decimal) -> None:
        super().__init__("La tasa del día cambió mientras armaba la venta. Revise los precios y cobre de nuevo.")
        self.new_rate = new_rate


@dataclass(frozen=True, slots=True)
class Shortage:
    product_id: int
    code: str
    name: str
    stock: Decimal
    requested: Decimal


class InsufficientStockError(ValueError):
    """RN-09: la venta deja existencias negativas. Se puede cobrar igual con la clave de la dueña."""

    def __init__(self, shortages: list[Shortage]) -> None:
        detail = "; ".join(
            f"{s.code} {s.name}: hay {s.stock.normalize():f}, pide {s.requested.normalize():f}" for s in shortages
        )
        super().__init__(f"No hay suficiente existencia. {detail}.")
        self.shortages = shortages


class CreditLimitError(ValueError):
    """RN-07: la deuda nueva supera el límite del cliente. Se puede fiar igual con la clave de la dueña."""

    def __init__(self, customer: str, limit: Decimal, balance: Decimal, new_debt: Decimal) -> None:
        super().__init__(
            f"{customer} tiene un límite de fiado de {format_usd(limit)}. Debe {format_usd(balance)} y esta venta "
            f"agrega {format_usd(new_debt)}."
        )
        self.limit = limit
        self.balance = balance
        self.new_debt = new_debt


@dataclass(frozen=True, slots=True)
class CartItem:
    product_id: int
    qty: Decimal


@dataclass(frozen=True, slots=True)
class LineQuote:
    """Renglón calculado para mostrar en la pantalla de venta (sin costo)."""

    product_id: int
    code: str
    description: str
    unit: str
    allows_fraction: bool
    qty: Decimal
    stock: Decimal
    unit_price_usd: Decimal
    unit_price_ves: Decimal
    line_total_ves: Decimal
    line_total_usd: Decimal


@dataclass(frozen=True, slots=True)
class SaleTotals:
    ves: DocumentTotals
    usd: DocumentTotals


# ------------------------------------------------------------------ cotizar


def _sellable(conn: sqlite3.Connection, product_id: int) -> Product:
    product = products_repo.get(conn, product_id)
    if product is None:
        raise LookupError("El producto no existe.")
    if not product.active:
        raise ValueError(f"{product.code} — {product.name} está inactivo y no se puede vender.")
    return product


def quote_line(conn: sqlite3.Connection, product_id: int, qty: Decimal, rate: Decimal) -> LineQuote:
    """RN-03 y RN-04 con la tasa de la venta."""
    product = _sellable(conn, product_id)
    check_quantity(qty, product.data.allows_fraction)
    multiple = settings_service.load(conn).rounding_multiple
    price_ves = unit_price_ves(product.data.price_usd, rate, multiple)
    lt = line_totals(qty, price_ves, product.data.price_usd, product.data.cost_usd)
    return LineQuote(
        product_id=product.id,
        code=product.code,
        description=product.name,
        unit=product.data.unit.value,
        allows_fraction=product.data.allows_fraction,
        qty=qty,
        stock=product.stock,
        unit_price_usd=product.data.price_usd,
        unit_price_ves=price_ves,
        line_total_ves=lt.total_ves,
        line_total_usd=lt.total_usd,
    )


def totals(lines: list[LineQuote]) -> SaleTotals:
    """RN-05: base e IVA sobre el total del documento."""
    return SaleTotals(
        ves=document_totals([q.line_total_ves for q in lines]),
        usd=document_totals([q.line_total_usd for q in lines]),
    )


# ------------------------------------------------------------------ cobrar


def _valid_owner(conn: sqlite3.Connection, user_id: int | None) -> bool:
    if user_id is None:
        return False
    u = users_repo.get(conn, user_id)
    return u is not None and u.is_owner and u.active


def charge(
    conn: sqlite3.Connection,
    user: User,
    items: list[CartItem],
    payments: list[PaymentInput],
    rate: Decimal,
    customer_id: int = customers_repo.FINAL_CONSUMER_ID,
    change_usd: Decimal = ZERO,
    authorized_by: int | None = None,
    today: date | None = None,
    on_credit: bool = False,
) -> Sale:
    """RF-52: cobra la venta. Lanza InsufficientStockError o CreditLimitError (para pedir la clave de la dueña)
    o RateChangedError.

    ``on_credit``: lo que no se pagó va a fiado (RF-71, RN-07): la deuda se guarda en USD con la tasa de la venta.
    """
    if not items:
        raise ValueError("La venta no tiene productos.")
    for p in payments:
        check_payment(p)

    with transaction(conn):
        session = cash_service.require_open_session(conn)
        current = rate_service.require_rate(conn, today)
        if current.rate != rate:
            raise RateChangedError(current.rate)
        settings = settings_service.load(conn)
        if any(p.method is PaymentMethod.USDT for p in payments) and not settings.payment_usdt_enabled:
            raise ValueError("Binance USDT no está activado como forma de pago.")
        customer = customers_repo.get(conn, customer_id)
        if customer is None or not customer.active:
            raise LookupError("El cliente no existe.")
        if on_credit and (customer.is_final_consumer or not customer.credit_enabled):
            raise ValueError(
                "Este cliente no tiene fiado habilitado. Elija un cliente con fiado (la dueña lo habilita en Fiado)."
            )

        products: dict[int, Product] = {}
        requested: dict[int, Decimal] = defaultdict(lambda: ZERO)
        lines = []
        for item in items:
            product = products.get(item.product_id) or _sellable(conn, item.product_id)
            products[product.id] = product
            check_quantity(item.qty, product.data.allows_fraction)
            price_ves = unit_price_ves(product.data.price_usd, rate, settings.rounding_multiple)
            lt = line_totals(item.qty, price_ves, product.data.price_usd, product.data.cost_usd)
            lines.append((product, item.qty, price_ves, lt))
            requested[product.id] += item.qty

        if len({p.data.vat_rate_bp for p, *_ in lines}) != 1:
            raise ValueError("Esta versión no admite productos con alícuotas de IVA distintas en la misma venta.")
        vat_bp = lines[0][0].data.vat_rate_bp

        shortages = [
            Shortage(pid, products[pid].code, products[pid].name, products[pid].stock, qty)
            for pid, qty in requested.items()
            if products[pid].stock - qty < 0
        ]
        if shortages and not settings.allow_negative_stock and not _valid_owner(conn, authorized_by):
            raise InsufficientStockError(shortages)

        t_ves = document_totals([lt.total_ves for *_, lt in lines], vat_bp)
        t_usd = document_totals([lt.total_usd for *_, lt in lines], vat_bp)
        credit_ves = credit_usd = ZERO
        over_limit = False
        if on_credit:
            if change_usd != 0:
                raise ValueError("Una venta a fiado no lleva vuelto.")
            rows, credit_ves = credit_rows(t_ves.total, payments, rate)
            credit_usd = credit_debt_usd(credit_ves, rate)
            balance = credit_repo.customer_balance(conn, customer.id)
            if not within_limit(customer.credit_limit_usd, balance, credit_usd):
                over_limit = True
                if not _valid_owner(conn, authorized_by):
                    assert customer.credit_limit_usd is not None
                    raise CreditLimitError(customer.name, customer.credit_limit_usd, balance, credit_usd)
        else:
            rows = payment_rows(t_ves.total, payments, rate, change_usd)

        number = sequences.take_next(conn, "NE")
        sale_id = repo.insert_sale(
            conn,
            number,
            session.id,
            customer.id,
            user.id,
            rate,
            t_ves.total,
            t_ves.base,
            t_ves.vat,
            t_usd.total,
            t_usd.base,
            credit_usd,
            credit_ves,
        )
        for product, qty, price_ves, lt in lines:
            repo.insert_item(
                conn,
                sale_id,
                product.id,
                product.name,
                qty,
                product.data.price_usd,
                price_ves,
                lt.total_ves,
                lt.total_usd,
                product.data.cost_usd,
                lt.cost_usd,
                product.data.vat_rate_bp,
            )
            apply_movement(conn, product.id, MovementType.SALE, -qty, user.id, sale_id=sale_id)
        for row in rows:
            repo.insert_payment(conn, session.id, row, sale_id=sale_id)
        if on_credit:
            days = customer.credit_days or settings.default_credit_days
            credit_repo.insert_receivable(conn, sale_id, customer.id, credit_usd, due_date(today or date.today(), days))
            if over_limit:
                audit(
                    conn,
                    user.id,
                    "CREDIT_LIMIT_EXCEEDED",
                    "sale",
                    sale_id,
                    {
                        "nota": f"NE-{number:06d}",
                        "cliente": customer.name,
                        "limite_usd": customer.credit_limit_usd,
                        "deuda_nueva_usd": credit_usd,
                    },
                    authorized_by=authorized_by,
                )
        if shortages:
            audit(
                conn,
                user.id,
                "SALE_WITHOUT_STOCK",
                "sale",
                sale_id,
                {
                    "nota": f"NE-{number:06d}",
                    "productos": [{"codigo": s.code, "existencia": s.stock, "vendido": s.requested} for s in shortages],
                    "por_configuracion": settings.allow_negative_stock and not _valid_owner(conn, authorized_by),
                },
                authorized_by=authorized_by if _valid_owner(conn, authorized_by) else None,
            )
    sale = repo.get(conn, sale_id)
    assert sale is not None
    return sale


# ------------------------------------------------------------------ anular (RF-53, RN-14)


def void_sale(
    conn: sqlite3.Connection, user: User, sale_id: int, reason: str, authorized_by: int | None = None
) -> None:
    """Solo mientras la caja de la venta siga abierta. Dueña, o vendedor con la clave de la dueña."""
    reason = " ".join(reason.split())
    if not reason:
        raise ValueError("Escriba el motivo de la anulación.")
    with transaction(conn):
        if not user.is_owner and not _valid_owner(conn, authorized_by):
            raise PermissionError("Para anular una venta hace falta la autorización de la dueña.")
        sale = repo.get(conn, sale_id)
        if sale is None:
            raise LookupError("La venta no existe.")
        if sale.voided:
            raise ValueError(f"La nota {sale.doc_number} ya está anulada.")
        open_session = cash_service.current_session(conn)
        if open_session is None or open_session.id != sale.session_id:
            raise ValueError("Esa venta es de una caja ya cerrada: no se anula. Corrija con un ajuste de inventario.")
        receivable = credit_repo.receivable_of_sale(conn, sale_id)
        if receivable is not None:
            if credit_repo.active_allocations_count(conn, receivable.id):
                raise ValueError(
                    "La deuda de esta venta ya tiene abonos. Anule primero los abonos o corrija con un ajuste."
                )
            credit_repo.void_receivable(conn, receivable.id)
        for item in sale.items:
            apply_movement(
                conn, item.product_id, MovementType.SALE_VOID, item.qty, user.id, sale_id=sale_id, reason=reason
            )
        repo.set_voided(conn, sale_id, user.id, reason)
        audit(
            conn,
            user.id,
            "SALE_VOID",
            "sale",
            sale_id,
            {"nota": sale.doc_number, "total_bs": sale.total_ves, "motivo": reason},
            authorized_by=None if user.is_owner else authorized_by,
        )


# ------------------------------------------------------------------ consultas (RF-56)


def _hide_costs(sale: Sale) -> Sale:
    return replace(sale, items=tuple(replace(i, unit_cost_usd=None, line_cost_usd=None) for i in sale.items))


def get_sale(conn: sqlite3.Connection, user: User, sale_id: int) -> Sale:
    """El vendedor solo ve sus ventas y nunca los costos."""
    sale = repo.get(conn, sale_id)
    if sale is None:
        raise LookupError("La venta no existe.")
    if user.is_owner:
        return sale
    if sale.user_id != user.id:
        raise PermissionError("Solo puede ver sus propias ventas.")
    return _hide_costs(sale)


def list_sales(conn: sqlite3.Connection, user: User, day: date | None = None) -> list[Sale]:
    """Ventas del día (sin renglones). El vendedor ve solo las suyas."""
    return repo.list_by_date(conn, day or date.today(), None if user.is_owner else user.id)
