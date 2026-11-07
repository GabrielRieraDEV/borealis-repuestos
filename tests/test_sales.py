"""Fase 3: criterios 1, 3, 4 y 5 del PRD §7 de punta a punta contra la base (servicio), e invariantes 2, 3, 6, 7 y 8."""

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal as D

import pytest

from repuestos.db.repositories import products as products_repo
from repuestos.domain.products import ProductData, Unit
from repuestos.domain.sale import PaymentInput as P
from repuestos.domain.sale import PaymentMethod as M
from repuestos.services import cash_service, product_service, rate_service, sale_service, settings_service
from repuestos.services.sale_service import CartItem, InsufficientStockError, RateChangedError
from tests.helpers import as_seller, make_seller, pastillas
from tests.invariants import all_violations

RATE = D("231.0468")


@pytest.fixture
def shop(conn: sqlite3.Connection, owner):
    """Tasa 231,0468, múltiplo 5, caja abierta con 20 USD y Bs 500 (criterio 5)."""
    rate_service.set_manual_rate(conn, owner, RATE)
    a = product_service.create_product(conn, owner, pastillas(conn, price_usd=D("12.50"), cost_usd=D("7")), D("10"))
    b = product_service.create_product(
        conn,
        owner,
        ProductData(
            name="Cable eléctrico", unit=Unit.METRO, allows_fraction=True, price_usd=D("0.80"), cost_usd=D("0.3")
        ),
        D("100"),
    )
    session = cash_service.open_session(conn, owner, D("20.00"), D("500.00"))
    return {"a": a, "b": b, "session": session}


def stock(conn, pid) -> D:
    return products_repo.get(conn, pid).stock


def sell(conn, user, *items: tuple[int, str], pays=None, change_usd="0", **kw):
    pays = pays if pays is not None else [P(M.CASH_VES, D("100000"))]
    return sale_service.charge(
        conn, user, [CartItem(pid, D(q)) for pid, q in items], pays, RATE, change_usd=D(change_usd), **kw
    )


def assert_ok(conn) -> None:
    assert all_violations(conn) == []


# ------------------------------------------------------------------ criterios del PRD


def test_criterio_1_inventario_resta_y_anular_devuelve(conn, owner, shop) -> None:
    a = shop["a"]
    sale = sell(conn, owner, (a.id, "3"))
    assert stock(conn, a.id) == D("7")
    sale_service.void_sale(conn, owner, sale.id, "Cliente se arrepintió")
    assert stock(conn, a.id) == D("10")
    assert_ok(conn)


def test_criterio_3_precio_en_bs(conn, owner, shop) -> None:
    q = sale_service.quote_line(conn, shop["a"].id, D("1"), RATE)
    assert q.unit_price_ves == D("2890.00")
    sale = sell(conn, owner, (shop["a"].id, "1"))
    assert sale.items[0].unit_price_ves == D("2890.00")
    assert (sale.total_ves, sale.base_ves, sale.vat_ves) == (D("2890.00"), D("2491.38"), D("398.62"))
    assert (sale.total_usd, sale.base_usd) == (D("12.50"), D("10.78"))


def test_criterio_4_pago_mixto_y_vuelto(conn, owner, shop) -> None:
    """Total Bs 2.890,00; paga 15 USD; recibe 2 USD y el resto en Bs → Bs 113,61."""
    sale = sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CASH_USD, D("15"))], change_usd="2")
    rows = [(p.method.value, p.amount, p.amount_ves, p.is_change) for p in sale.payments]
    assert rows == [
        ("CASH_USD", D("15.00"), D("3465.70"), False),
        ("CASH_USD", D("-2.00"), D("-462.09"), True),
        ("CASH_VES", D("-113.61"), D("-113.61"), True),
    ]
    assert_ok(conn)


def test_criterio_5_caja_cuadra(conn, owner, shop) -> None:
    """Apertura 20 USD y Bs 500; venta del criterio 4 → esperado 33,00 USD y Bs 386,39."""
    sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CASH_USD, D("15"))], change_usd="2")
    s = cash_service.session_summary(conn, owner, shop["session"].id)
    assert (s.expected_usd, s.expected_ves) == (D("33.00"), D("386.39"))
    cash_service.close_session(conn, owner, D("33.00"), D("386.39"))
    closed = cash_service.session_summary(conn, owner, shop["session"].id)
    assert (closed.difference_usd, closed.difference_ves) == (D("0.00"), D("0.00"))
    assert_ok(conn)


def test_venta_1_del_resumen_del_mes(conn, owner) -> None:
    """Plan Fase 5, venta 1: 3 A a 15,00 + 2,5 m B → Bs 10.872,50; ref 47,00; costo 33,75."""
    rate_service.set_manual_rate(conn, owner, RATE)
    a = product_service.create_product(conn, owner, pastillas(conn, price_usd=D("15"), cost_usd=D("11")), D("15"))
    b = product_service.create_product(
        conn,
        owner,
        ProductData(name="Cable", unit=Unit.METRO, allows_fraction=True, price_usd=D("0.80"), cost_usd=D("0.30")),
        D("100"),
    )
    cash_service.open_session(conn, owner, D("0"), D("0"))
    sale = sell(conn, owner, (a.id, "3"), (b.id, "2.5"), pays=[P(M.POS, D("10872.50"))])
    assert (sale.total_ves, sale.total_usd, sale.vat_ves, sale.base_usd) == (
        D("10872.50"),
        D("47.00"),
        D("1499.66"),
        D("40.52"),
    )
    assert [i.unit_price_ves for i in sale.items] == [D("3470.00"), D("185.00")]
    assert sum(i.line_cost_usd for i in sale.items) == D("33.75")
    assert stock(conn, b.id) == D("97.5")


# ------------------------------------------------------------------ cobro


def test_copia_precio_y_costo_al_vender(conn, owner, shop) -> None:
    sale = sell(conn, owner, (shop["a"].id, "2"))
    item = sale.items[0]
    assert (item.description, item.unit_price_usd, item.unit_cost_usd, item.line_cost_usd) == (
        "Pastillas de freno delanteras — Bera 150",
        D("12.5000"),
        D("7.0000"),
        D("14.00"),
    )
    product_service.update_product(conn, owner, shop["a"].id, pastillas(conn, price_usd=D("20"), name="Otro nombre"))
    again = sale_service.get_sale(conn, owner, sale.id)
    assert again.items[0].description.startswith("Pastillas") and again.items[0].unit_price_usd == D("12.5")


def test_fraccion(conn, owner, shop) -> None:
    sale = sell(conn, owner, (shop["b"].id, "2.5"))
    assert sale.items[0].line_total_ves == D("462.50")
    with pytest.raises(ValueError, match="unidades completas"):
        sell(conn, owner, (shop["a"].id, "1.5"))


def test_pagos_mixtos_bs_punto_movil(conn, owner, shop) -> None:
    pays = [P(M.CASH_VES, D("890")), P(M.POS, D("1000")), P(M.MOBILE, D("1000"), "0412-123")]
    sale = sell(conn, owner, (shop["a"].id, "1"), pays=pays)
    assert [p.reference for p in sale.payments] == ["", "", "0412-123"]
    assert not any(p.is_change for p in sale.payments)
    assert_ok(conn)


def test_vuelto_todo_en_bs(conn, owner, shop) -> None:
    sale = sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CASH_VES, D("3000"))])
    assert [(p.method.value, p.amount) for p in sale.payments if p.is_change] == [("CASH_VES", D("-110.00"))]


def test_vuelto_que_excede_se_rechaza(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="mayor que el vuelto"):
        sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CASH_USD, D("15"))], change_usd="3")
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0


def test_pago_insuficiente_se_rechaza(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="falta"):
        sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CASH_VES, D("2889.99"))])
    with pytest.raises(ValueError, match="falta"):
        sell(conn, owner, (shop["a"].id, "1"), pays=[])


def test_usdt_solo_si_esta_activo(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="USDT"):
        sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.USDT, D("13"))])
    settings_service.save(conn, owner, replace(settings_service.load(conn), payment_usdt_enabled=True))
    sale = sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.USDT, D("13"))])
    assert sale.payments[0].amount_ves == D("3003.61")


def test_fiado_no_disponible_en_esta_fase(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="fiado"):
        sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CREDIT, D("13"))])


def test_requiere_caja_abierta_y_tasa(conn, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn), D("5"))
    with pytest.raises(LookupError, match="caja"):
        sell(conn, owner, (p.id, "1"))
    cash_service.open_session(conn, owner, D("0"), D("0"))
    with pytest.raises(LookupError, match="tasa"):
        sell(conn, owner, (p.id, "1"))


def test_tasa_cambiada_durante_la_venta(conn, owner, shop) -> None:
    rate_service.set_manual_rate(conn, owner, D("240"))
    with pytest.raises(RateChangedError) as e:
        sell(conn, owner, (shop["a"].id, "1"))
    assert e.value.new_rate == D("240")


def test_producto_inactivo(conn, owner, shop) -> None:
    product_service.set_active(conn, owner, shop["a"].id, False)
    with pytest.raises(ValueError, match="inactivo"):
        sell(conn, owner, (shop["a"].id, "1"))


# ------------------------------------------------------------------ existencia insuficiente (RN-09)


def test_existencia_insuficiente_bloquea(conn, owner, shop) -> None:
    with pytest.raises(InsufficientStockError) as e:
        sell(conn, owner, (shop["a"].id, "6"), (shop["a"].id, "5"))  # suma por producto: 11 > 10
    assert e.value.shortages[0].requested == D("11")
    assert "R-00001" in str(e.value) and "hay 10" in str(e.value)
    assert stock(conn, shop["a"].id) == D("10")


def test_existencia_insuficiente_con_clave_de_la_duena(conn, owner, shop) -> None:
    seller = make_seller(conn, owner)
    with pytest.raises(InsufficientStockError):
        sell(conn, seller, (shop["a"].id, "12"))
    with pytest.raises(InsufficientStockError):  # un id que no es de la dueña no autoriza
        sell(conn, seller, (shop["a"].id, "12"), authorized_by=seller.id)
    sale = sell(conn, seller, (shop["a"].id, "12"), authorized_by=owner.id)
    assert stock(conn, shop["a"].id) == D("-2")
    row = conn.execute(
        "SELECT user_id, authorized_by, details_json FROM audit_log WHERE action = 'SALE_WITHOUT_STOCK'"
    ).fetchone()
    assert (row[0], row[1]) == (seller.id, owner.id)
    assert json.loads(row[2])["nota"] == sale.doc_number
    assert_ok(conn)


def test_existencia_negativa_permitida_por_configuracion(conn, owner, shop) -> None:
    settings_service.save(conn, owner, replace(settings_service.load(conn), allow_negative_stock=True))
    sell(conn, owner, (shop["a"].id, "11"))
    assert stock(conn, shop["a"].id) == D("-1")
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'SALE_WITHOUT_STOCK'").fetchone()[0] == 1


# ------------------------------------------------------------------ correlativos (RN-12, invariante 7)


def test_correlativos_sin_huecos_aunque_una_venta_falle(conn, owner, shop, monkeypatch) -> None:
    s1 = sell(conn, owner, (shop["a"].id, "1"))
    import repuestos.services.sale_service as svc

    real = svc.apply_movement
    calls = {"n": 0}

    def failing(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("se fue la luz a mitad de la venta")
        return real(*args, **kwargs)

    monkeypatch.setattr(svc, "apply_movement", failing)
    with pytest.raises(RuntimeError):
        sell(conn, owner, (shop["a"].id, "1"), (shop["b"].id, "1"))
    monkeypatch.setattr(svc, "apply_movement", real)
    s2 = sell(conn, owner, (shop["a"].id, "1"))
    assert (s1.doc_number, s2.doc_number) == ("NE-000001", "NE-000002")
    assert stock(conn, shop["a"].id) == D("8")  # la venta fallida no dejó nada a medias
    assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 4  # 2 ventas × (pago + vuelto)
    assert_ok(conn)


# ------------------------------------------------------------------ anulación (RF-53, RN-14, invariante 8)


def test_anular_anula_pagos_y_conserva_numero(conn, owner, shop) -> None:
    sale = sell(conn, owner, (shop["a"].id, "1"), pays=[P(M.CASH_USD, D("15"))], change_usd="2")
    sale_service.void_sale(conn, owner, sale.id, "error")
    voided = sale_service.get_sale(conn, owner, sale.id)
    assert voided.voided and voided.doc_number == "NE-000001"
    assert all(p.voided for p in voided.payments)
    s = cash_service.session_summary(conn, owner, shop["session"].id)
    assert (s.expected_usd, s.expected_ves, s.voided_count) == (D("20.00"), D("500.00"), 1)
    assert sell(conn, owner, (shop["a"].id, "1")).doc_number == "NE-000002"
    assert_ok(conn)


def test_vendedor_anula_solo_con_autorizacion(conn, owner, shop) -> None:
    seller = make_seller(conn, owner)
    sale = sell(conn, seller, (shop["a"].id, "1"))
    with pytest.raises(PermissionError):
        sale_service.void_sale(conn, seller, sale.id, "error")
    sale_service.void_sale(conn, seller, sale.id, "error", authorized_by=owner.id)
    row = conn.execute("SELECT user_id, authorized_by FROM audit_log WHERE action = 'SALE_VOID'").fetchone()
    assert tuple(row) == (seller.id, owner.id)


def test_no_se_anula_con_caja_cerrada_ni_dos_veces(conn, owner, shop) -> None:
    sale = sell(conn, owner, (shop["a"].id, "1"))
    with pytest.raises(ValueError, match="motivo"):
        sale_service.void_sale(conn, owner, sale.id, " ")
    sale_service.void_sale(conn, owner, sale.id, "x")
    with pytest.raises(ValueError, match="ya está anulada"):
        sale_service.void_sale(conn, owner, sale.id, "x")
    other = sell(conn, owner, (shop["a"].id, "1"))
    cash_service.close_session(conn, owner, D("0"), D("0"))
    cash_service.open_session(conn, owner, D("0"), D("0"))
    with pytest.raises(ValueError, match="caja ya cerrada"):
        sale_service.void_sale(conn, owner, other.id, "x")
    assert_ok(conn)


# ------------------------------------------------------------------ permisos y consultas


def test_vendedor_no_ve_costos_ni_ventas_ajenas(conn, owner, shop) -> None:
    seller = make_seller(conn, owner)
    mine = sell(conn, seller, (shop["a"].id, "1"))
    theirs = sell(conn, owner, (shop["a"].id, "1"))
    view = sale_service.get_sale(conn, seller, mine.id)
    assert view.items[0].unit_cost_usd is None and view.items[0].line_cost_usd is None
    with pytest.raises(PermissionError):
        sale_service.get_sale(conn, seller, theirs.id)
    assert [s.id for s in sale_service.list_sales(conn, seller)] == [mine.id]
    assert [s.id for s in sale_service.list_sales(conn, owner)] == [theirs.id, mine.id]


# ------------------------------------------------------------------ caja (RF-60 a RF-63, RN-11)


def test_una_sola_caja_abierta(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="Ya hay una caja abierta"):
        cash_service.open_session(conn, owner, D("0"), D("0"))


def test_entradas_salidas_y_cierre_ciego(conn, owner, shop) -> None:
    seller = make_seller(conn, owner)
    cash_service.add_movement(conn, seller, "OUT", "VES", D("100"), "Pago de agua")
    cash_service.add_movement(conn, seller, "IN", "USD", D("5"), "Cambio traído de la casa")
    sell(conn, seller, (shop["a"].id, "1"), pays=[P(M.CASH_USD, D("15"))], change_usd="2")
    sell(conn, seller, (shop["a"].id, "1"), pays=[P(M.POS, D("2890"))])
    with pytest.raises(PermissionError):
        cash_service.session_summary(conn, seller, shop["session"].id)
    blind = cash_service.blind_summary(conn, shop["session"].id)
    assert blind.expected_usd is None and blind.difference_usd is None
    result = cash_service.close_session(conn, seller, D("37.00"), D("280.00"), "faltó un billete")
    assert not hasattr(result, "expected_usd")
    s = cash_service.session_summary(conn, owner, shop["session"].id)
    assert (s.expected_usd, s.expected_ves) == (D("38.00"), D("286.39"))  # 20+15-2+5 ; 500-113,61-100
    assert (s.difference_usd, s.difference_ves) == (D("-1.00"), D("-6.39"))
    pos = next(n for n in s.non_cash if n.method is M.POS)
    assert (pos.total, pos.count) == (D("2890.00"), 1)
    assert (s.sales_count, s.sales_total_ves) == (2, D("5780.00"))
    assert cash_service.current_session(conn) is None
    with pytest.raises(LookupError, match="caja"):
        sell(conn, owner, (shop["a"].id, "1"))
    history = cash_service.history(conn, owner)
    assert history[0].counted_usd == D("37.00") and history[0].expected_usd == D("38.00")
    with pytest.raises(PermissionError):
        cash_service.history(conn, seller)
    audit = json.loads(conn.execute("SELECT details_json FROM audit_log WHERE action = 'CASH_CLOSE'").fetchone()[0])
    assert audit["diferencia_bs"] == "-6.39"
    assert_ok(conn)


def test_validaciones_de_caja(conn, owner, shop) -> None:
    with pytest.raises(ValueError, match="motivo"):
        cash_service.add_movement(conn, owner, "OUT", "USD", D("1"), "")
    with pytest.raises(ValueError, match="mayor que cero"):
        cash_service.add_movement(conn, owner, "OUT", "USD", D("0"), "x")
    with pytest.raises(ValueError, match="negativo"):
        cash_service.close_session(conn, owner, D("-1"), D("0"))


def test_la_caja_sigue_abierta_al_reabrir(tmp_path, owner, shop) -> None:
    """RF-60: si el programa se cierra con la caja abierta, al volver sigue la misma."""
    session = shop["session"]
    path = tmp_path / "test.db"
    from repuestos.db.connection import connect

    other = connect(path)
    assert cash_service.current_session(other).id == session.id
    other.close()


def test_seller_can_open_and_close(conn, owner) -> None:
    seller = as_seller(owner)
    s = cash_service.open_session(conn, seller, D("1"), D("2"))
    cash_service.close_session(conn, seller, D("1"), D("2"))
    assert cash_service.history(conn, owner)[0].id == s.id
