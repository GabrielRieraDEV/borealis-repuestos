"""Fase 4 · fiado: criterio 6 del PRD, FIFO, límite, abonos en caja (RN-11) e invariantes 3, 4 y 5."""

import json
import sqlite3
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from repuestos.domain.credit import Allocation, allocate_fifo, due_date, is_overdue, within_limit
from repuestos.domain.sale import PaymentInput as P
from repuestos.domain.sale import PaymentMethod as M
from repuestos.services import (
    cash_service,
    credit_service,
    customer_service,
    print_service,
    product_service,
    rate_service,
    sale_service,
)
from repuestos.services.sale_service import CartItem, CreditLimitError
from tests.helpers import as_seller, make_seller, pastillas
from tests.invariants import all_violations

RATE = D("231.0468")
TODAY = date.today()


@pytest.fixture
def shop(conn: sqlite3.Connection, owner):
    rate_service.set_manual_rate(conn, owner, RATE)
    a = product_service.create_product(conn, owner, pastillas(conn, price_usd=D("12.50")), D("100"))
    session = cash_service.open_session(conn, owner, D("20"), D("500"))
    c = customer_service.create(conn, owner, "José Pérez", "V12345678")
    c = credit_service.set_customer_credit(conn, owner, c.id, True)
    return {"a": a, "customer": c, "session": session}


def fiar(conn, user, shop, qty="1", pays=(), **kw):
    """Venta de Bs 2.890,00 por unidad, con lo pagado y el resto a fiado."""
    return sale_service.charge(
        conn,
        user,
        [CartItem(shop["a"].id, D(qty))],
        list(pays),
        RATE,
        kw.pop("customer_id", shop["customer"].id),
        on_credit=True,
        **kw,
    )


def assert_ok(conn) -> None:
    assert all_violations(conn) == []


# ------------------------------------------------------------------ dominio


def test_dominio_fifo_vencimiento_y_limite() -> None:
    assert allocate_fifo(D("15"), [(1, D("12.51")), (2, D("12.51"))]) == [
        Allocation(1, D("12.51")),
        Allocation(2, D("2.49")),
    ]
    with pytest.raises(ValueError, match="mayor que la deuda: el saldo total es USD 25,02"):
        allocate_fifo(D("25.03"), [(1, D("12.51")), (2, D("12.51"))])
    assert due_date(date(2026, 11, 7), 15) == date(2026, 11, 22)
    assert not is_overdue(date(2026, 11, 22), D("1"), date(2026, 11, 22))
    assert is_overdue(date(2026, 11, 22), D("1"), date(2026, 11, 23))
    assert not is_overdue(date(2026, 11, 22), D("0"), date(2026, 12, 1))
    assert within_limit(None, D("100"), D("100"))
    assert within_limit(D("20"), D("7.49"), D("12.51"))
    assert not within_limit(D("20"), D("7.50"), D("12.51"))


# ------------------------------------------------------------------ criterio 6


def test_criterio_6_fiado_en_usd_y_abono(conn, owner, shop) -> None:
    """Venta a fiado de Bs 2.890,00 a 231,0468 → 12,51 USD. Con tasa 240,00 abona Bs 1.200,00 → 5,00 USD, saldo 7,51."""
    sale = fiar(conn, owner, shop)
    assert (sale.credit_ves, sale.credit_usd) == (D("2890.00"), D("12.51"))
    st = credit_service.statement(conn, shop["customer"].id)
    assert st.balance_usd == D("12.51")
    assert st.debts[0].receivable.due_date == TODAY + timedelta(days=15)

    rate_service.set_manual_rate(conn, owner, D("240.00"))
    preview = credit_service.preview_payment(conn, shop["customer"].id, M.CASH_VES, D("1200.00"))
    assert (preview.amount_usd, preview.balance_after) == (D("5.00"), D("7.51"))
    ab = credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_VES, D("1200.00"))
    assert (ab.doc_number, ab.amount_usd, ab.rate) == ("AB-000001", D("5.00"), D("240.000000"))
    assert credit_service.customer_balance(conn, shop["customer"].id) == D("7.51")
    assert sale_service.get_sale(conn, owner, sale.id).credit_usd == D("12.51")  # la deuda no cambia con la tasa
    assert_ok(conn)


def test_fiado_parcial(conn, owner, shop) -> None:
    sale = fiar(conn, owner, shop, pays=[P(M.CASH_VES, D("1000"))])
    assert (sale.credit_ves, sale.credit_usd) == (D("1890.00"), D("8.18"))  # 1.890 / 231,0468 = 8,1801…
    assert sum(p.amount_ves for p in sale.payments) + sale.credit_ves == sale.total_ves
    assert_ok(conn)


def test_plazo_del_cliente(conn, owner, shop) -> None:
    credit_service.set_customer_credit(conn, owner, shop["customer"].id, True, days=30)
    fiar(conn, owner, shop)
    st = credit_service.statement(conn, shop["customer"].id)
    assert st.debts[0].receivable.due_date == TODAY + timedelta(days=30)


@pytest.mark.parametrize("who", ["final", "sin_fiado"])
def test_cliente_sin_fiado(conn, owner, shop, who) -> None:
    cid = 1 if who == "final" else customer_service.create(conn, owner, "Ana", "V999999").id
    with pytest.raises(ValueError, match="no tiene fiado"):
        fiar(conn, owner, shop, customer_id=cid)
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0


def test_fiado_sin_vuelto_ni_pago_completo(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="no lleva vuelto"):
        fiar(conn, owner, shop, pays=[P(M.CASH_USD, D("5"))], change_usd=D("1"))
    with pytest.raises(ValueError, match="pagada completa"):
        fiar(conn, owner, shop, pays=[P(M.CASH_USD, D("13"))])


def test_consumidor_final_nunca_tiene_fiado(conn, owner) -> None:
    with pytest.raises(ValueError, match="nunca"):
        credit_service.set_customer_credit(conn, owner, 1, True)


def test_vendedor_no_habilita_fiado_pero_vende_y_cobra(conn, owner, shop) -> None:
    seller = make_seller(conn, owner)
    with pytest.raises(PermissionError):
        credit_service.set_customer_credit(conn, seller, shop["customer"].id, True)
    fiar(conn, seller, shop)
    ab = credit_service.register_payment(conn, seller, shop["customer"].id, M.POS, D("1000"))
    assert ab.user_name == "Pedro Pérez"


# ------------------------------------------------------------------ límite


def test_limite_bloquea_salvo_clave_de_la_duena(conn, owner, shop) -> None:
    credit_service.set_customer_credit(conn, owner, shop["customer"].id, True, limit_usd=D("20"))
    fiar(conn, owner, shop)  # 12,51
    seller = make_seller(conn, owner)
    with pytest.raises(CreditLimitError) as e:
        fiar(conn, seller, shop)  # 25,02 > 20
    assert "límite de fiado de USD 20,00" in str(e.value)
    sale = fiar(conn, seller, shop, authorized_by=owner.id)
    row = conn.execute(
        "SELECT user_id, authorized_by, details_json FROM audit_log WHERE action = 'CREDIT_LIMIT_EXCEEDED'"
    ).fetchone()
    assert (row[0], row[1]) == (seller.id, owner.id)
    assert json.loads(row[2])["nota"] == sale.doc_number
    assert credit_service.customer_balance(conn, shop["customer"].id) == D("25.02")


# ------------------------------------------------------------------ abonos


def test_abono_fifo_con_dos_deudas(conn, owner, shop) -> None:
    s1 = fiar(conn, owner, shop)
    s2 = fiar(conn, owner, shop)
    ab = credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("15"))
    assert [(a.sale_number, a.amount_usd) for a in ab.allocations] == [(s1.number, D("12.51")), (s2.number, D("2.49"))]
    st = credit_service.statement(conn, shop["customer"].id)
    by_sale = {d.receivable.sale_id: d.receivable for d in st.debts}
    assert (by_sale[s1.id].status, by_sale[s1.id].balance_usd) == ("PAID", D("0.00"))
    assert (by_sale[s2.id].status, by_sale[s2.id].balance_usd) == ("OPEN", D("10.02"))
    assert_ok(conn)


def test_abono_mayor_que_el_saldo_rechazado(conn, owner, shop) -> None:
    fiar(conn, owner, shop)
    with pytest.raises(ValueError, match="mayor que la deuda"):
        credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("12.52"))
    credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("12.51"))
    assert credit_service.customer_balance(conn, shop["customer"].id) == 0
    with pytest.raises(ValueError, match="no tiene deudas"):
        credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("1"))
    assert conn.execute("SELECT next_number FROM doc_sequences WHERE doc_type = 'AB'").fetchone()[0] == 2
    assert_ok(conn)


def test_abono_validaciones(conn, owner, shop) -> None:
    fiar(conn, owner, shop)
    cid = shop["customer"].id
    with pytest.raises(ValueError, match="fiado"):
        credit_service.register_payment(conn, owner, cid, M.CREDIT, D("1"))
    with pytest.raises(ValueError, match="USDT"):
        credit_service.register_payment(conn, owner, cid, M.USDT, D("1"))
    with pytest.raises(ValueError, match="2 decimales"):
        credit_service.register_payment(conn, owner, cid, M.CASH_USD, D("1.001"))
    cash_service.close_session(conn, owner, D("0"), D("0"))
    with pytest.raises(LookupError, match="caja"):
        credit_service.register_payment(conn, owner, cid, M.CASH_USD, D("1"))


def test_abonos_en_efectivo_entran_al_arqueo(conn, owner, shop) -> None:
    """RN-11: el abono entra a la caja abierta como cualquier pago."""
    fiar(conn, owner, shop)
    credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("5"))
    credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_VES, D("462.09"))  # 2,00 USD
    credit_service.register_payment(conn, owner, shop["customer"].id, M.MOBILE, D("231.05"))  # 1,00 USD
    s = cash_service.session_summary(conn, owner, shop["session"].id)
    assert (s.expected_usd, s.expected_ves) == (D("25.00"), D("962.09"))
    mobile = next(n for n in s.non_cash if n.method is M.MOBILE)
    assert (mobile.total, mobile.count) == (D("231.05"), 1)
    assert credit_service.customer_balance(conn, shop["customer"].id) == D("4.51")
    assert_ok(conn)


# ------------------------------------------------------------------ anulaciones (RN-07, RN-14)


def test_anular_abono_revierte_reparto_y_caja(conn, owner, shop) -> None:
    s1 = fiar(conn, owner, shop)
    fiar(conn, owner, shop)
    ab = credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("15"))
    with pytest.raises(PermissionError):
        credit_service.void_payment(conn, as_seller(owner), ab.id, "error")
    with pytest.raises(ValueError, match="motivo"):
        credit_service.void_payment(conn, owner, ab.id, " ")
    credit_service.void_payment(conn, owner, ab.id, "Billete falso")
    st = credit_service.statement(conn, shop["customer"].id)
    assert st.balance_usd == D("25.02")
    assert all(d.receivable.status == "OPEN" for d in st.debts)
    assert st.payments[0].voided
    assert cash_service.session_summary(conn, owner, shop["session"].id).expected_usd == D("20.00")
    with pytest.raises(ValueError, match="ya está anulado"):
        credit_service.void_payment(conn, owner, ab.id, "x")
    # sin abonos activos, la venta ya se puede anular y su deuda queda anulada
    sale_service.void_sale(conn, owner, s1.id, "devolución")
    assert credit_service.customer_balance(conn, shop["customer"].id) == D("12.51")
    assert_ok(conn)


def test_anular_venta_a_fiado(conn, owner, shop) -> None:
    sale = fiar(conn, owner, shop, pays=[P(M.CASH_VES, D("1000"))])
    sale_service.void_sale(conn, owner, sale.id, "se arrepintió")
    st = credit_service.statement(conn, shop["customer"].id)
    assert st.debts[0].receivable.status == "VOIDED" and st.balance_usd == 0
    assert_ok(conn)


def test_venta_con_abonos_no_se_anula(conn, owner, shop) -> None:
    sale = fiar(conn, owner, shop)
    credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("1"))
    with pytest.raises(ValueError, match="La deuda de esta venta ya tiene abonos"):
        sale_service.void_sale(conn, owner, sale.id, "x")
    assert not sale_service.get_sale(conn, owner, sale.id).voided
    assert_ok(conn)


def test_abono_de_caja_cerrada_no_se_anula(conn, owner, shop) -> None:
    fiar(conn, owner, shop)
    ab = credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_USD, D("1"))
    cash_service.close_session(conn, owner, D("21"), D("500"))
    cash_service.open_session(conn, owner, D("0"), D("0"))
    with pytest.raises(ValueError, match="caja ya cerrada"):
        credit_service.void_payment(conn, owner, ab.id, "x")


# ------------------------------------------------------------------ estado de cuenta y deudores (RF-73)


def test_vencidas_deudores_y_total(conn, owner, shop) -> None:
    old = fiar(conn, owner, shop, today=TODAY)  # vence en 15 días
    other = customer_service.create(conn, owner, "Ana", "V999999")
    credit_service.set_customer_credit(conn, owner, other.id, True, days=1)
    fiar(conn, owner, shop, customer_id=other.id)
    later = TODAY + timedelta(days=5)
    st = credit_service.statement(conn, other.id, today=later)
    assert st.overdue_usd == D("12.51") and st.debts[0].overdue
    assert not credit_service.statement(conn, shop["customer"].id, today=later).debts[0].overdue
    rows = credit_service.debtors(conn, today=later)
    assert [(r.name, r.balance_usd, r.overdue_usd) for r in rows] == [
        ("Ana", D("12.51"), D("12.51")),
        ("José Pérez", D("12.51"), D("0.00")),
    ]
    assert credit_service.total_receivable(conn) == D("25.02")
    assert old.doc_number == "NE-000001"


# ------------------------------------------------------------------ tickets


def test_nota_de_entrega_con_fiado_y_comprobante_de_abono(conn, owner, shop) -> None:
    sale = fiar(conn, owner, shop)
    text = "\n".join(print_service.sale_lines(conn, owner, sale.id))
    assert "Fiado" in text and "USD 12,51" in text
    assert f"Vence: {(TODAY + timedelta(days=15)).strftime('%d/%m/%Y')}" in text
    rate_service.set_manual_rate(conn, owner, D("240.00"))
    ab = credit_service.register_payment(conn, owner, shop["customer"].id, M.CASH_VES, D("1200.00"))
    lines = print_service.credit_receipt_lines(conn, ab.id)
    receipt = "\n".join(lines)
    assert all(len(line) <= 48 for line in lines)
    for expected in ["COMPROBANTE DE ABONO", "Nro: AB-000001", "Cliente: José Pérez", "C.I./RIF: V-12345678"]:
        assert expected in receipt
    assert any(line.startswith("ABONO") and line.endswith("USD 5,00") for line in lines)
    assert any(line.strip().startswith("NE-000001") and line.endswith("USD 5,00") for line in lines)
    assert any(line.startswith("SALDO PENDIENTE") and line.endswith("USD 7,51") for line in lines)
    assert any(line.startswith("Efectivo Bs") and line.endswith("Bs 1.200,00") for line in lines)
