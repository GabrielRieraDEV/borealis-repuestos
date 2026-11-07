"""Reportes en PDF (RF-80 a RF-84) con reportlab: encabezado del negocio, fecha de emisión y paginado."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from repuestos.db.repositories.inventory import ToOrderLine
from repuestos.domain.products import UNIT_SHORT, Unit
from repuestos.domain.sale import METHOD_LABELS, PaymentMethod
from repuestos.formatting import format_date, format_number, format_usd, format_ves
from repuestos.printing.ticket import BusinessHeader
from repuestos.services.report_service import DailySales, MonthSummary, PeriodSales, ValuedInventory

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]  # fmt: skip

_styles = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=_styles["Title"], fontSize=15, spaceAfter=4)
SUB = ParagraphStyle("s", parent=_styles["Normal"], fontSize=9, textColor=colors.HexColor("#444444"))
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=4)
NORMAL = ParagraphStyle("n", parent=_styles["Normal"], fontSize=9)
GRID = colors.HexColor("#b0b0b0")
HEAD_BG = colors.HexColor("#e8eef7")
GRID_WIDTH = mm / 5  # línea fina de la tabla (~0,6 pt)


def month_name(year_month: str) -> str:
    y, m = year_month.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def _qty(value: Decimal, fraction: bool, unit: str) -> str:
    digits = format_number(value, 3).rstrip("0").rstrip(",") if fraction else format_number(value, 0)
    return f"{digits} {UNIT_SHORT[Unit(unit)]}"


class _NumberedCanvas(Canvas):
    """Pie con "Página N de M": guarda las páginas y las numera al final."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self) -> None:  # noqa: N802
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#666666"))
            self.drawRightString(letter[0] - 15 * mm, 10 * mm, f"Página {self._pageNumber} de {total}")
            super().showPage()
        super().save()


def _table(data: Sequence[Sequence[object]], widths: Sequence[int], right_cols: Sequence[int] = (), bold_last=False):
    rows = [[Paragraph(str(c), NORMAL) if isinstance(c, str) and len(c) > 45 else c for c in row] for row in data]
    t = Table(rows, colWidths=[w * mm for w in widths], repeatRows=1)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("GRID", (0, 0), (-1, -1), GRID_WIDTH, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for col in right_cols:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    if bold_last:
        style.append(("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9))
    t.setStyle(TableStyle(style))
    return t


def _build(path: Path, business: BusinessHeader, title: str, subtitle: str, story: list[Flowable]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path), pagesize=letter, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
        title=title, author=business.name,
    )  # fmt: skip
    head = [
        Paragraph(f"<b>{business.name}</b>", NORMAL),
        Paragraph(
            " · ".join(
                x
                for x in (
                    f"RIF {business.rif}" if business.rif else "",
                    business.address,
                    f"Telf. {business.phone}" if business.phone else "",
                )
                if x
            ),
            SUB,
        ),  # fmt: skip
        Spacer(1, 4 * mm),
        Paragraph(title, TITLE),
        Paragraph(f"{subtitle} · Emitido el {datetime.now().strftime('%d/%m/%Y %H:%M')}", SUB),
        Spacer(1, 4 * mm),
    ]
    doc.build(head + story, canvasmaker=_NumberedCanvas)
    return path


# ------------------------------------------------------------------ RF-80


def daily_sales_pdf(path: Path, business: BusinessHeader, d: DailySales) -> Path:
    who = f"Solo las ventas de {d.only_user}" if d.only_user else "Todas las ventas"
    story: list[Flowable] = [
        _table(
            [
                ["Notas de entrega", "Total Bs", "Referencia USD", "Fiado Bs", "Fiado USD"],
                [
                    str(d.count),
                    format_ves(d.total_ves),
                    format_usd(d.total_usd),
                    format_ves(d.credit_ves),
                    format_usd(d.credit_usd),
                ],
            ],  # fmt: skip
            [30, 40, 35, 40, 35],
            right_cols=(0, 1, 2, 3, 4),
        ),
        Paragraph("Por forma de pago (neto de vuelto)", H2),
    ]
    rows: list[list[object]] = [["Forma de pago", "Cobros", "Monto", "Equivale Bs"]]
    for m in d.by_method:
        amount = (
            format_usd(m.amount) if m.method in (PaymentMethod.CASH_USD, PaymentMethod.USDT) else format_ves(m.amount)
        )
        rows.append([METHOD_LABELS[m.method], str(m.count), amount, format_ves(m.amount_ves)])
    if d.credit_ves:
        rows.append(["Fiado", "", format_usd(d.credit_usd), format_ves(d.credit_ves)])
    story.append(_table(rows, [60, 25, 45, 50], right_cols=(1, 2, 3)))
    if not d.only_user:
        story.append(Paragraph("Por vendedor", H2))
        rows = [["Vendedor", "Notas", "Total Bs", "Referencia USD"]]
        rows += [[s.name, str(s.count), format_ves(s.total_ves), format_usd(s.total_usd)] for s in d.by_seller]
        story.append(_table(rows, [70, 25, 45, 40], right_cols=(1, 2, 3)))
    story.append(Paragraph("Notas de entrega", H2))
    rows = [["Nota", "Hora", "Cliente", "Vendedor", "Total Bs", "Ref. USD"]]
    rows += [
        [f"NE-{s.number:06d}", s.created_at[11:16], s.customer_name, s.user_name, format_ves(s.total_ves),
         format_usd(s.total_usd)]
        for s in d.sales
    ]  # fmt: skip
    story.append(_table(rows, [24, 14, 52, 36, 32, 27], right_cols=(4, 5)))
    if d.voided:
        story.append(Paragraph("Anuladas (no suman)", H2))
        rows = [["Nota", "Hora", "Total Bs", "Motivo"]]
        rows += [
            [f"NE-{s.number:06d}", s.created_at[11:16], format_ves(s.total_ves), s.void_reason or ""] for s in d.voided
        ]
        story.append(_table(rows, [25, 15, 35, 110], right_cols=(2,)))
    return _build(path, business, "Ventas del día", f"{format_date(d.day)} · {who}", story)


# ------------------------------------------------------------------ RF-81


def period_sales_pdf(path: Path, business: BusinessHeader, p: PeriodSales) -> Path:
    rows: list[list[object]] = [["Día", "Notas", "Base imponible Bs", "IVA Bs", "Total con IVA Bs", "Ref. USD"]]
    rows += [
        [format_date(d.day), str(d.count), format_ves(d.base_ves), format_ves(d.vat_ves), format_ves(d.total_ves),
         format_usd(d.total_usd)]
        for d in p.days
    ]  # fmt: skip
    rows.append(["TOTAL", str(p.count), format_ves(p.base_ves), format_ves(p.vat_ves), format_ves(p.total_ves),
                 format_usd(p.total_usd)])  # fmt: skip
    story: list[Flowable] = [
        Paragraph("Según notas de entrega (no fiscal).", NORMAL),
        Spacer(1, 3 * mm),
        _table(rows, [28, 18, 38, 32, 40, 29], right_cols=(1, 2, 3, 4, 5), bold_last=True),
    ]
    return _build(path, business, "Monto vendido", f"Del {format_date(p.start)} al {format_date(p.end)}", story)


# ------------------------------------------------------------------ RF-82


def month_summary_pdf(path: Path, business: BusinessHeader, s: MonthSummary) -> Path:
    f = s.figures
    prev = format_usd(s.inventory_prev_close_usd) if s.inventory_prev_close_usd is not None else "sin dato"
    rows: list[list[object]] = [
        ["Concepto", "USD", "Bs"],
        ["Inversión en mercancía al cierre del mes anterior", prev, ""],
        ["Inversión en mercancía hoy", format_usd(s.inventory_today_usd), ""],
        ["Compras del mes", format_usd(f.purchases_usd), ""],
        ["Ventas con IVA", format_usd(f.sales_usd), format_ves(f.sales_ves)],
        ["IVA", format_usd(f.vat_usd), format_ves(f.vat_ves)],
        ["Ventas netas", format_usd(f.net_usd), format_ves(f.net_ves)],
        ["Costo de lo vendido", format_usd(f.cost_usd), ""],
        ["Ganancia bruta", format_usd(f.gross_profit_usd), ""],
        ["Pérdidas (dañado, faltante, uso interno)", format_usd(f.losses_usd), ""],
        ["Faltantes de conteo", format_usd(f.count_shortage_usd), ""],
        ["Por cobrar (fiado)", format_usd(s.receivable_usd), ""],
        ["Resultado del mes antes de gastos", format_usd(f.result_usd), ""],
    ]
    table = _table(rows, [100, 40, 40], right_cols=(1, 2), bold_last=True)
    table.setStyle(TableStyle([("FONT", (0, 8), (-1, 8), "Helvetica-Bold", 9)]))
    hist: list[list[object]] = [
        ["Mes", "Compras", "Ventas netas", "Ganancia bruta", "Resultado", "Inversión al cierre"]
    ]
    for h in s.history:
        close = format_usd(h.inventory_close_usd) if h.inventory_close_usd is not None else "sin dato"
        hist.append([month_name(h.year_month), format_usd(h.figures.purchases_usd), format_usd(h.figures.net_usd),
                     format_usd(h.figures.gross_profit_usd), format_usd(h.figures.result_usd), close])  # fmt: skip
    story: list[Flowable] = [
        table,
        Paragraph(
            f"{f.sales_count} nota{'s' if f.sales_count != 1 else ''} de entrega en el mes."
            " Montos en USD; las ventas también en Bs.",
            SUB,
        ),
        Paragraph("Últimos 12 meses", H2),
        _table(hist, [34, 28, 30, 30, 28, 35], right_cols=(1, 2, 3, 4, 5)),
    ]
    title = f"Resumen del mes · {month_name(f'{s.year:04d}-{s.month:02d}')}"
    return _build(path, business, title, "Cuánto tengo invertido, cuánto compré, cuánto vendí y cuánto me quedó", story)


# ------------------------------------------------------------------ RF-83


def valued_inventory_pdf(path: Path, business: BusinessHeader, inv: ValuedInventory) -> Path:
    rows: list[list[object]] = [["Código", "Producto", "Categoría", "Existencia", "Costo USD", "Valor USD"]]
    rows += [
        [p.code, p.name, p.category_name, _qty(p.stock, p.allows_fraction, p.unit), format_usd(p.cost_usd, 4),
         format_usd(p.value_usd)]
        for p in inv.products
    ]  # fmt: skip
    rows.append(["", "TOTAL", "", "", "", format_usd(inv.total_usd)])
    story: list[Flowable] = [
        Paragraph(f"Inversión en mercancía: <b>{format_usd(inv.total_usd)}</b> (existencia × costo promedio).", NORMAL),
        Spacer(1, 3 * mm),
        _table(rows, [20, 70, 30, 22, 20, 23], right_cols=(3, 4, 5), bold_last=True),
    ]
    if inv.without_cost:
        story.append(Paragraph(f"Productos sin costo cargado ({len(inv.without_cost)})", H2))
        story.append(Paragraph("No suman a la inversión. Cargue su costo en la ficha del producto.", SUB))
        rows = [["Código", "Producto", "Existencia"]]
        rows += [[p.code, p.name, _qty(p.stock, p.allows_fraction, p.unit)] for p in inv.without_cost]
        story.append(_table(rows, [25, 120, 30], right_cols=(2,)))
    return _build(path, business, "Inventario valorizado", "Productos activos", story)


# ------------------------------------------------------------------ RF-84


def to_order_pdf(path: Path, business: BusinessHeader, lines: list[ToOrderLine]) -> Path:
    rows: list[list[object]] = [["Código", "Producto", "Existencia", "Mínimo", "Último proveedor", "Último costo"]]
    previous = None
    category_rows = []
    for line in lines:
        category = line.category_name or "(sin categoría)"
        if category != previous:
            rows.append([category, "", "", "", "", ""])
            category_rows.append(len(rows) - 1)
            previous = category
        rows.append([
            line.code, line.name, _qty(line.stock, line.allows_fraction, line.unit),
            _qty(line.min_stock, line.allows_fraction, line.unit), line.last_supplier or "—",
            format_usd(line.last_cost, 4) if line.last_cost is not None else "—",
        ])  # fmt: skip
    table = _table(rows, [20, 68, 20, 18, 34, 25], right_cols=(2, 3, 5))
    table.setStyle(
        TableStyle(
            [("FONT", (0, r), (-1, r), "Helvetica-Bold", 9) for r in category_rows]
            + [("SPAN", (0, r), (-1, r)) for r in category_rows]
            + [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f4f4f4")) for r in category_rows]
        )
    )
    story: list[Flowable] = [
        Paragraph(f"{len(lines)} productos en el mínimo o por debajo.", NORMAL),
        Spacer(1, 3 * mm),
        table,
    ]
    return _build(path, business, "Para pedir", "Existencia en el mínimo o por debajo, por categoría", story)
