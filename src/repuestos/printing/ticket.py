"""Texto de los tickets de 80 mm (48 columnas): nota de entrega (RN-12) y cierre de caja (RF-62).

Funciones puras: reciben los datos y devuelven líneas de texto. El envío a la impresora está en ``printer.py``.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from decimal import Decimal

from repuestos.db.repositories.sales import Sale
from repuestos.domain.money import from_db
from repuestos.domain.sale import METHOD_LABELS, PaymentMethod
from repuestos.formatting import format_date, format_number, format_rate, format_usd, format_ves

WIDTH = 48
RULE = "-" * WIDTH

# La impresora usa páginas de códigos de 8 bits: se evitan caracteres que no existen en ellas.
_REPLACE = str.maketrans({"—": "-", "–": "-", "·": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "*"})


@dataclass(frozen=True, slots=True)
class BusinessHeader:
    name: str
    rif: str
    address: str
    phone: str


def clean(text: str) -> str:
    return text.translate(_REPLACE)


def center(text: str) -> list[str]:
    return [line.center(WIDTH).rstrip() for line in textwrap.wrap(clean(text), WIDTH)] or [""]


def lr(left: str, right: str) -> str:
    """Texto a la izquierda y monto a la derecha; si no cabe, el monto va en la línea siguiente."""
    left, right = clean(left), clean(right)
    if len(left) + 1 + len(right) <= WIDTH:
        return left + " " * (WIDTH - len(left) - len(right)) + right
    return left[:WIDTH] + "\n" + right.rjust(WIDTH)


def wrap(text: str, indent: str = "") -> list[str]:
    return textwrap.wrap(clean(text), WIDTH, subsequent_indent=indent) or [""]


def _header(b: BusinessHeader) -> list[str]:
    lines = center(b.name)
    if b.rif:
        lines += center(f"RIF {b.rif}")
    if b.address:
        lines += center(b.address)
    if b.phone:
        lines += center(f"Telf. {b.phone}")
    return lines


def _qty(q: Decimal) -> str:
    text = format_number(q, 3).rstrip("0").rstrip(",")
    return text


def _id_doc(doc: str | None) -> str:
    return f"{doc[0]}-{doc[1:]}" if doc else ""


def _datetime(ts: str) -> str:
    return f"{format_date(ts)} {ts[11:16]}"


def sale_ticket(
    sale: Sale,
    business: BusinessHeader,
    reprint: bool = False,
    credit_due_date: str | None = None,
) -> list[str]:
    """Nota de entrega (RN-12)."""
    out = _header(business)
    out.append(RULE)
    out += center("NOTA DE ENTREGA - NO VALIDA COMO FACTURA")
    if sale.voided:
        out += center("*** ANULADA ***")
    elif reprint:
        out += center("(reimpresión)")
    out.append(lr(f"Nro: {sale.doc_number}", _datetime(sale.created_at)))
    out += wrap(f"Vendedor: {sale.user_name}")
    out += wrap(f"Cliente: {sale.customer_name}")
    if sale.customer_id_doc:
        out.append(f"C.I./RIF: {_id_doc(sale.customer_id_doc)}")
    out.append(RULE)
    out.append(lr("Cant x Precio unit. Bs", "Total Bs"))
    out.append(RULE)
    for item in sale.items:
        out += wrap(item.description, "  ")
        out.append(
            lr(f"  {_qty(item.qty)} x {format_number(item.unit_price_ves, 2)}", format_number(item.line_total_ves, 2))
        )
    out.append(RULE)
    vat_pct = format_number(from_db(sale.items[0].vat_rate_bp, "bp") if sale.items else Decimal(16), 0)
    out.append(lr("Base imponible", format_ves(sale.base_ves)))
    out.append(lr(f"IVA {vat_pct}%", format_ves(sale.vat_ves)))
    out.append(lr("TOTAL", format_ves(sale.total_ves)))
    out.append(lr("Referencia", format_usd(sale.total_usd)))
    out.append(lr("Tasa BCV", format_rate(sale.rate)))
    out.append(RULE)
    out.append("Formas de pago:")
    for p in sale.payments:
        if p.is_change:
            continue
        label = METHOD_LABELS[p.method]
        if p.currency == "USD":
            label += f" {format_number(p.amount, 2)}"
        if p.reference:
            label += f" Ref. {p.reference}"
        out.append(lr("  " + label, format_ves(p.amount_ves)))
    change = [p for p in sale.payments if p.is_change]
    if change:
        for p in change:
            amount = format_usd(-p.amount) if p.currency == "USD" else format_ves(-p.amount)
            out.append(lr(f"  Vuelto {METHOD_LABELS[p.method].split()[-1]}", amount))
    if sale.credit_usd > 0:
        out.append(lr("  Fiado", format_usd(sale.credit_usd)))
        if credit_due_date:
            out.append(f"  Vence: {format_date(credit_due_date)}")
    out.append(RULE)
    out += center("Gracias por su compra")
    return out


@dataclass(frozen=True, slots=True)
class CloseTicketData:
    session_id: int
    opened_at: str
    opened_by: str
    closed_at: str | None
    closed_by: str | None
    opening_usd: Decimal
    opening_ves: Decimal
    sales_count: int
    voided_count: int
    sales_total_ves: Decimal
    non_cash: list[tuple[PaymentMethod, Decimal, int]]
    in_usd: Decimal
    out_usd: Decimal
    in_ves: Decimal
    out_ves: Decimal
    counted_usd: Decimal | None
    counted_ves: Decimal | None
    expected_usd: Decimal | None = None  # solo si lo imprime la dueña
    expected_ves: Decimal | None = None


def close_ticket(d: CloseTicketData, business: BusinessHeader) -> list[str]:
    out = _header(business)
    out.append(RULE)
    out += center("CIERRE DE CAJA")
    out.append(f"Caja Nro. {d.session_id}")
    out.append(f"Abrió: {d.opened_by} {_datetime(d.opened_at)}")
    if d.closed_at:
        out.append(f"Cerró: {d.closed_by} {_datetime(d.closed_at)}")
    out.append(RULE)
    out.append(lr("Ventas", str(d.sales_count)))
    out.append(lr("Anuladas", str(d.voided_count)))
    out.append(lr("Total vendido", format_ves(d.sales_total_ves)))
    out.append(RULE)
    out.append("Para verificar con el banco:")
    for method, total, count in d.non_cash:
        amount = format_usd(total) if method is PaymentMethod.USDT else format_ves(total)
        out.append(lr(f"  {METHOD_LABELS[method]} ({count})", amount))
    out.append(RULE)
    out.append(lr("Apertura USD", format_usd(d.opening_usd)))
    out.append(lr("Apertura Bs", format_ves(d.opening_ves)))
    if d.in_usd or d.out_usd:
        out.append(lr("Entradas / salidas USD", f"{format_number(d.in_usd, 2)} / {format_number(d.out_usd, 2)}"))
    if d.in_ves or d.out_ves:
        out.append(lr("Entradas / salidas Bs", f"{format_number(d.in_ves, 2)} / {format_number(d.out_ves, 2)}"))
    if d.counted_usd is not None and d.counted_ves is not None:
        out.append(lr("Contado USD", format_usd(d.counted_usd)))
        out.append(lr("Contado Bs", format_ves(d.counted_ves)))
    if d.expected_usd is not None and d.expected_ves is not None:
        out.append(RULE)
        out.append(lr("Esperado USD", format_usd(d.expected_usd)))
        out.append(lr("Esperado Bs", format_ves(d.expected_ves)))
        if d.counted_usd is not None and d.counted_ves is not None:
            out.append(lr("Diferencia USD", format_usd(d.counted_usd - d.expected_usd)))
            out.append(lr("Diferencia Bs", format_ves(d.counted_ves - d.expected_ves)))
    out.append(RULE)
    out.append("")
    out.append("Firma: ______________________________")
    return out


def as_text(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class CreditReceiptData:
    doc_number: str
    created_at: str
    cashier: str
    customer_name: str
    customer_id_doc: str | None
    payments: list[tuple[PaymentMethod, str, Decimal, Decimal, str]]  # método, moneda, monto, equiv. Bs, ref.
    rate: Decimal
    amount_usd: Decimal
    applied: list[tuple[str, Decimal]]  # (NE-000001, USD aplicado)
    balance_after: Decimal
    voided: bool = False


def credit_receipt(d: CreditReceiptData, business: BusinessHeader, reprint: bool = False) -> list[str]:
    """Comprobante de abono AB-000001 (RF-72)."""
    out = _header(business)
    out.append(RULE)
    out += center("COMPROBANTE DE ABONO")
    if d.voided:
        out += center("*** ANULADO ***")
    elif reprint:
        out += center("(reimpresión)")
    out.append(lr(f"Nro: {d.doc_number}", _datetime(d.created_at)))
    out += wrap(f"Recibió: {d.cashier}")
    out += wrap(f"Cliente: {d.customer_name}")
    if d.customer_id_doc:
        out.append(f"C.I./RIF: {_id_doc(d.customer_id_doc)}")
    out.append(RULE)
    for method, currency, amount, amount_ves, ref in d.payments:
        label = METHOD_LABELS[method] + (f" Ref. {ref}" if ref else "")
        shown = format_usd(amount) if currency == "USD" else format_ves(amount)
        out.append(lr(label, shown))
        if currency == "USD":
            out.append(lr("  equivale a", format_ves(amount_ves)))
    out.append(lr("Tasa BCV", format_rate(d.rate)))
    out.append(lr("ABONO", format_usd(d.amount_usd)))
    out.append(RULE)
    out.append("Aplicado a:")
    for doc, amount in d.applied:
        out.append(lr(f"  {doc}", format_usd(amount)))
    out.append(RULE)
    out.append(lr("SALDO PENDIENTE", format_usd(d.balance_after)))
    out.append(RULE)
    out += center("Gracias por su pago")
    return out
