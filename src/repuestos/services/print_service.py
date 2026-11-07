"""Imprimir y guardar tickets (RF-54, RF-56, RF-62). Siempre después del COMMIT del documento."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repuestos.config import get_paths
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


def sale_lines(conn: sqlite3.Connection, user: User, sale_id: int, reprint: bool = False) -> list[str]:
    sale = sale_service.get_sale(conn, user, sale_id)
    return sale_ticket(sale, business_header(conn), reprint=reprint)


def print_sale(conn: sqlite3.Connection, user: User, sale_id: int, reprint: bool = False) -> None:
    """Lanza PrintError si la impresora no responde (la venta ya está guardada)."""
    printer.send_to_printer(settings_service.load(conn).printer_name, sale_lines(conn, user, sale_id, reprint))


def save_sale_pdf(conn: sqlite3.Connection, user: User, sale_id: int, folder: Path | None = None) -> Path:
    sale = sale_service.get_sale(conn, user, sale_id)
    lines = sale_ticket(sale, business_header(conn), reprint=True)
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
