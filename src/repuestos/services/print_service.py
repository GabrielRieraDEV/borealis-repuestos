"""Imprimir y guardar tickets (RF-54, RF-56, RF-62). Siempre después del COMMIT del documento."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repuestos.config import get_paths
from repuestos.db.repositories import credit as credit_repo
from repuestos.domain.users import User
from repuestos.printing import printer
from repuestos.printing.ticket import BusinessHeader, CloseTicketData, close_ticket, sale_ticket
from repuestos.services import cash_service, sale_service, settings_service

PrintError = printer.PrintError


def business_header(conn: sqlite3.Connection) -> BusinessHeader:
    s = settings_service.load(conn)
    return BusinessHeader(s.business_name, s.business_rif, s.business_address, s.business_phone)


def tickets_dir() -> Path:
    return get_paths().base / "tickets"


# ------------------------------------------------------------------ nota de entrega


def _due(conn: sqlite3.Connection, sale_id: int) -> str | None:
    receivable = credit_repo.receivable_of_sale(conn, sale_id)
    return receivable.due_date.isoformat() if receivable else None


def sale_lines(conn: sqlite3.Connection, user: User, sale_id: int, reprint: bool = False) -> list[str]:
    sale = sale_service.get_sale(conn, user, sale_id)
    return sale_ticket(sale, business_header(conn), reprint=reprint, credit_due_date=_due(conn, sale_id))


def print_sale(conn: sqlite3.Connection, user: User, sale_id: int, reprint: bool = False) -> None:
    """Lanza PrintError si la impresora no responde (la venta ya está guardada)."""
    printer.send_to_printer(settings_service.load(conn).printer_name, sale_lines(conn, user, sale_id, reprint))


def save_sale_pdf(conn: sqlite3.Connection, user: User, sale_id: int, folder: Path | None = None) -> Path:
    sale = sale_service.get_sale(conn, user, sale_id)
    lines = sale_ticket(sale, business_header(conn), reprint=True, credit_due_date=_due(conn, sale_id))
    return printer.save_pdf((folder or tickets_dir()) / f"{sale.doc_number}.pdf", lines, sale.doc_number)


# ------------------------------------------------------------------ cierre de caja


def close_lines(conn: sqlite3.Connection, user: User, session_id: int) -> list[str]:
    """El ticket de cierre lleva lo esperado y la diferencia solo si lo pide la dueña (cierre ciego)."""
    s = (
        cash_service.session_summary(conn, user, session_id)
        if user.is_owner
        else cash_service.blind_summary(conn, session_id)
    )
    session = s.session
    data = CloseTicketData(
        session_id=session.id,
        opened_at=session.opened_at,
        opened_by=session.opened_by_name,
        closed_at=session.closed_at,
        closed_by=session.closed_by_name,
        opening_usd=session.opening_usd,
        opening_ves=session.opening_ves,
        sales_count=s.sales_count,
        voided_count=s.voided_count,
        sales_total_ves=s.sales_total_ves,
        non_cash=[(n.method, n.total, n.count) for n in s.non_cash],
        in_usd=s.in_usd,
        out_usd=s.out_usd,
        in_ves=s.in_ves,
        out_ves=s.out_ves,
        counted_usd=session.counted_usd,
        counted_ves=session.counted_ves,
        expected_usd=s.expected_usd,
        expected_ves=s.expected_ves,
    )
    return close_ticket(data, business_header(conn))


def print_close(conn: sqlite3.Connection, user: User, session_id: int) -> None:
    printer.send_to_printer(settings_service.load(conn).printer_name, close_lines(conn, user, session_id))


def save_close_pdf(conn: sqlite3.Connection, user: User, session_id: int, folder: Path | None = None) -> Path:
    lines = close_lines(conn, user, session_id)
    return printer.save_pdf((folder or tickets_dir()) / f"cierre-caja-{session_id}.pdf", lines, f"Cierre {session_id}")


def print_test(conn: sqlite3.Connection, printer_name: str) -> None:
    """Página de prueba para configurar la térmica (visita de instalación)."""
    from repuestos.printing.ticket import RULE, center

    header = business_header(conn)
    lines = [*center(header.name or "Borealis Repuestos"), RULE, *center("PRUEBA DE IMPRESORA"), RULE]
    lines += ["Si lee esto completo, la impresora quedó lista.", "Acentos y eñes: áéíóú ñ Ñ ¿? ¡!", "0123456789" * 4]
    lines += [RULE, *center(printer_name)]
    printer.send_to_printer(printer_name, lines)


# ------------------------------------------------------------------ comprobante de abono


def credit_receipt_lines(conn: sqlite3.Connection, credit_payment_id: int, reprint: bool = False) -> list[str]:
    from repuestos.db.repositories import customers as customers_repo
    from repuestos.db.repositories import users as users_repo
    from repuestos.printing.ticket import CreditReceiptData, credit_receipt
    from repuestos.services import credit_service

    payment, rows = credit_service.payment_detail(conn, credit_payment_id)
    customer = customers_repo.get(conn, payment.customer_id)
    assert customer is not None
    cashier = users_repo.get(conn, payment.user_id)
    data = CreditReceiptData(
        doc_number=payment.doc_number,
        created_at=payment.created_at,
        cashier=cashier.full_name if cashier else "",
        customer_name=customer.name,
        customer_id_doc=customer.id_doc,
        payments=[(r.method, r.currency.value, r.amount, r.amount_ves, r.reference) for r in rows],
        rate=payment.rate,
        amount_usd=payment.amount_usd,
        applied=[(f"NE-{a.sale_number:06d}", a.amount_usd) for a in payment.allocations],
        balance_after=credit_service.customer_balance(conn, payment.customer_id),
        voided=payment.voided,
    )
    return credit_receipt(data, business_header(conn), reprint=reprint)


def print_credit_receipt(conn: sqlite3.Connection, credit_payment_id: int, reprint: bool = False) -> None:
    printer.send_to_printer(
        settings_service.load(conn).printer_name, credit_receipt_lines(conn, credit_payment_id, reprint)
    )


def save_credit_receipt_pdf(conn: sqlite3.Connection, credit_payment_id: int, folder: Path | None = None) -> Path:
    from repuestos.services import credit_service

    payment, _ = credit_service.payment_detail(conn, credit_payment_id)
    lines = credit_receipt_lines(conn, credit_payment_id, reprint=True)
    return printer.save_pdf((folder or tickets_dir()) / f"{payment.doc_number}.pdf", lines, payment.doc_number)
