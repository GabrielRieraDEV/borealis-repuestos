"""Fase 5 · reportes: el caso del resumen del mes del plan (criterio 8 del PRD) da exactamente esos números."""

import sqlite3
from datetime import date
from decimal import Decimal as D

import pytest

from repuestos.domain.inventory import AdjustmentKind
from repuestos.domain.products import ProductData, Unit
from repuestos.domain.sale import PaymentInput as P
from repuestos.domain.sale import PaymentMethod as M
from repuestos.services import (
    cash_service,
    inventory_service,
    product_service,
    purchase_service,
    rate_service,
    report_service,
    sale_service,
)
from repuestos.services.purchase_service import PurchaseLineInput
from repuestos.services.sale_service import CartItem
from tests.helpers import as_seller, make_seller

RATE = D("231.0468")
TODAY = date.today()


@pytest.fixture
def month_case(conn: sqlite3.Connection, owner):
    """Plan, Fase 5: mes sin foto del anterior, tasa 231,0468, múltiplo 5,00."""
    rate_service.set_manual_rate(conn, owner, RATE)
    cash_service.open_session(conn, owner, D("0"), D("0"))
    # 1 y 2: productos con existencia inicial
    a = product_service.create_product(
        conn, owner, ProductData(name="Pastillas de freno Bera 150", price_usd=D("15.00"), cost_usd=D("10.00")), D("10")
    )
    b = product_service.create_product(
        conn,
        owner,
        ProductData(
            name="Cable eléctrico", unit=Unit.METRO, allows_fraction=True, price_usd=D("0.80"), cost_usd=D("0.30")
        ),
        D("100"),
    )
    # 3: compra 5 A a 13,00 → costo 11,0000
    sup = purchase_service.create_supplier(conn, owner, "Distribuidora")
    purchase_service.register_purchase(conn, owner, sup.id, [PurchaseLineInput(a.id, D("5"), D("13.00"))], TODAY)
    # 4: venta 1: 3 A + 2,5 m B → Bs 10.872,50
    v1 = sale_service.charge(
        conn, owner, [CartItem(a.id, D("3")), CartItem(b.id, D("2.5"))], [P(M.POS, D("10872.50"))], RATE
    )
    assert v1.total_ves == D("10872.50")
    # 5: ajuste 2 m de B dañados
    inventory_service.adjust(conn, owner, b.id, AdjustmentKind.DAMAGE, D("2"), "dañado")
    # 6: venta 2: 1 A, anulada en la misma caja
    v2 = sale_service.charge(conn, owner, [CartItem(a.id, D("1"))], [P(M.POS, D("3470"))], RATE)
    sale_service.void_sale(conn, owner, v2.id, "prueba")
    return {"a": a, "b": b}


def test_caso_del_resumen_del_mes(conn, owner, month_case) -> None:
    s = report_service.month_summary(conn, owner, TODAY.year, TODAY.month)
    f = s.figures
    assert s.inventory_prev_close_usd is None  # "sin dato"
    assert s.inventory_today_usd == D("160.65")  # A: 12 × 11,00 = 132,00; B: 95,5 × 0,30 = 28,65
    assert f.purchases_usd == D("65.00")
    assert (f.sales_usd, f.sales_ves) == (D("47.00"), D("10872.50"))
    assert (f.vat_usd, f.vat_ves) == (D("6.48"), D("1499.66"))
    assert (f.net_usd, f.net_ves) == (D("40.52"), D("9372.84"))
    assert f.cost_usd == D("33.75")
    assert f.gross_profit_usd == D("6.77")
    assert f.losses_usd == D("0.60")
    assert s.receivable_usd == D("0.00")
    assert f.result_usd == D("6.17")
    assert f.sales_count == 1
    assert len(s.history) == 12 and s.history[0].year_month == f"{TODAY.year:04d}-{TODAY.month:02d}"
    assert s.history[0].inventory_close_usd == D("160.65")


def test_faltantes_de_conteo_aparte(conn, owner, month_case) -> None:
    from repuestos.services.inventory_service import CountEntry

    inventory_service.register_count(conn, owner, [CountEntry(month_case["a"].id, D("11"))])  # falta 1 a 11,00
    f = report_service.month_summary(conn, owner, TODAY.year, TODAY.month).figures
    assert (f.losses_usd, f.count_shortage_usd) == (D("0.60"), D("11.00"))
    assert f.result_usd == D("6.77") - D("0.60") - D("11.00")


def test_foto_mensual(conn, owner, month_case) -> None:
    # base con movimientos anteriores al mes que se simula: se toma la foto del mes anterior
    next_month = date(TODAY.year + (TODAY.month == 12), TODAY.month % 12 + 1, 3)
    ym = report_service.ensure_monthly_snapshot(conn, next_month)
    assert ym == f"{TODAY.year:04d}-{TODAY.month:02d}"
    assert report_service.ensure_monthly_snapshot(conn, next_month) is None  # una sola vez
    s = report_service.month_summary(conn, owner, next_month.year, next_month.month, today=next_month)
    assert s.inventory_prev_close_usd == D("160.65")


def test_sin_foto_en_base_recien_instalada(conn, owner) -> None:
    assert report_service.ensure_monthly_snapshot(conn, TODAY) is None


def test_inventario_valorizado(conn, owner, month_case) -> None:
    product_service.create_product(conn, owner, ProductData(name="Sin costo"), D("3"))
    inv = report_service.valued_inventory(conn, owner)
    assert inv.total_usd == D("160.65")
    assert [p.name for p in inv.without_cost] == ["Sin costo"]


def test_ventas_del_dia_y_periodo(conn, owner, month_case) -> None:
    d = report_service.daily_sales(conn, owner, TODAY)
    assert (d.count, d.total_ves, d.total_usd) == (1, D("10872.50"), D("47.00"))
    assert [(m.method, m.amount, m.count) for m in d.by_method] == [(M.POS, D("10872.50"), 1)]
    assert [(v.number, v.total_ves) for v in d.voided] == [(2, D("3470.00"))]
    assert d.by_seller[0].count == 1
    p = report_service.period_sales(conn, owner, TODAY, TODAY)
    assert (p.count, p.total_ves, p.base_ves, p.vat_ves) == (1, D("10872.50"), D("9372.84"), D("1499.66"))


def test_vendedor_solo_sus_ventas_y_sin_reportes_de_costo(conn, owner, month_case) -> None:
    seller = make_seller(conn, owner)
    sale_service.charge(conn, seller, [CartItem(month_case["a"].id, D("1"))], [P(M.CASH_VES, D("3470"))], RATE)
    d = report_service.daily_sales(conn, seller, TODAY)
    assert (d.count, d.total_ves, d.only_user) == (1, D("3470.00"), "Pedro Pérez")
    s = as_seller(owner)
    for call in (
        lambda: report_service.month_summary(conn, s, TODAY.year, TODAY.month),
        lambda: report_service.valued_inventory(conn, s),
        lambda: report_service.period_sales(conn, s, TODAY, TODAY),
        lambda: report_service.to_order(conn, s),
    ):
        with pytest.raises(PermissionError):
            call()


def test_pdfs_de_reportes(conn, owner, month_case, tmp_path) -> None:
    from repuestos.services import print_service

    paths = [
        print_service.daily_sales_pdf(conn, owner, TODAY, tmp_path),
        print_service.period_sales_pdf(conn, owner, TODAY.replace(day=1), TODAY, tmp_path),
        print_service.month_summary_pdf(conn, owner, TODAY.year, TODAY.month, tmp_path),
        print_service.valued_inventory_pdf(conn, owner, tmp_path),
        print_service.to_order_pdf(conn, owner, tmp_path),
        *print_service.cloud_pdfs(conn, tmp_path),
    ]
    for p in paths:
        assert p.exists() and p.read_bytes().startswith(b"%PDF"), p
    assert {p.name for p in paths[-2:]} == {"Inventario de hoy.pdf", "Resumen del mes.pdf"}
    seller = make_seller(conn, owner)
    assert print_service.daily_sales_pdf(conn, seller, TODAY, tmp_path).exists()
    with pytest.raises(PermissionError):
        print_service.valued_inventory_pdf(conn, seller, tmp_path)


def test_para_pedir_en_ticket(conn, owner, month_case) -> None:
    from repuestos.services import print_service

    product_service.create_product(conn, owner, ProductData(name="Bujía NGK", min_stock=D("10")), D("2"))
    lines = print_service.to_order_lines(conn, owner)
    text = "\n".join(lines)
    assert all(len(line) <= 48 for line in lines)
    assert "PARA PEDIR" in text and "Bujía NGK" in text and "hay 2 u / mín. 10" in text
    with pytest.raises(print_service.PrintError):
        print_service.print_to_order(conn, owner)  # sin impresora configurada
