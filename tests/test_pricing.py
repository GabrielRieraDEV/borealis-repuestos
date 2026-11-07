"""Cada ejemplo numérico de docs/02-reglas-de-negocio.md y los criterios 2 a 6 del PRD §7, con los valores exactos."""

from decimal import Decimal as D

import pytest

from repuestos.domain.cash import cash_difference, expected_cash
from repuestos.domain.pricing import (
    Currency,
    check_quantity,
    compute_change,
    credit_debt_usd,
    credit_payment_usd,
    document_totals,
    line_totals,
    pack_purchase,
    unit_price_ves,
    usd_reference,
    ves_equivalent,
    weighted_average_cost,
)

RATE = D("231.0468")
MULTIPLE = D("5.00")


# ------------------------------------------------------------------ RN-03 (criterio 3)


def test_rn03_precio_12_50_usd() -> None:
    """RN-03 y criterio 3: 12,50 USD × 231,0468 = 2.888,085 → Bs 2.890,00."""
    assert unit_price_ves(D("12.50"), RATE, MULTIPLE) == D("2890.00")


def test_rn03_precio_0_80_usd() -> None:
    """RN-03: 0,80 USD × 231,0468 = 184,83744 → Bs 185,00."""
    assert unit_price_ves(D("0.80"), RATE, MULTIPLE) == D("185.00")


def test_rn03_multiplo_un_centimo_redondea_hacia_arriba() -> None:
    """RN-03: con múltiplo 0,01 queda el redondeo hacia arriba al céntimo."""
    assert unit_price_ves(D("0.80"), RATE, D("0.01")) == D("184.84")
    assert unit_price_ves(D("12.50"), RATE, D("0.01")) == D("2888.09")


def test_rn03_resultado_con_dos_decimales() -> None:
    assert str(unit_price_ves(D("12.50"), RATE, MULTIPLE)) == "2890.00"


# ------------------------------------------------------------------ RN-04


def test_rn04_renglon_cable() -> None:
    """RN-04: 2,5 m de cable a Bs 185,00 → Bs 462,50."""
    lt = line_totals(D("2.5"), D("185.00"), D("0.80"), D("0.30"))
    assert lt.total_ves == D("462.50")
    assert lt.total_usd == D("2.00")
    assert lt.cost_usd == D("0.75")


def test_rn04_fraccion_solo_si_el_producto_lo_permite() -> None:
    check_quantity(D("2.5"), allows_fraction=True)
    check_quantity(D("3"), allows_fraction=False)
    with pytest.raises(ValueError):
        check_quantity(D("2.5"), allows_fraction=False)
    with pytest.raises(ValueError):
        check_quantity(D("1.2345"), allows_fraction=True)
    with pytest.raises(ValueError):
        check_quantity(D("0"), allows_fraction=True)


# ------------------------------------------------------------------ RN-05


def test_rn05_base_e_iva_sobre_el_total() -> None:
    """RN-05: total Bs 2.890,00 → base 2.491,38 → IVA 398,62."""
    t = document_totals([D("2890.00")])
    assert t.total == D("2890.00")
    assert t.base == D("2491.38")
    assert t.vat == D("398.62")
    assert t.base + t.vat == t.total


def test_rn05_venta_1_del_caso_del_resumen_del_mes() -> None:
    """Plan Fase 5, venta 1: 3 A (Bs 3.470,00) + 2,5 m B (Bs 185,00) → Bs 10.872,50; ref 47,00 USD."""
    price_a = unit_price_ves(D("15.00"), RATE, MULTIPLE)
    price_b = unit_price_ves(D("0.80"), RATE, MULTIPLE)
    assert price_a == D("3470.00")
    assert price_b == D("185.00")
    a = line_totals(D("3"), price_a, D("15.00"), D("11.0000"))
    b = line_totals(D("2.5"), price_b, D("0.80"), D("0.3000"))
    ves = document_totals([a.total_ves, b.total_ves])
    usd = document_totals([a.total_usd, b.total_usd])
    assert ves.total == D("10872.50")
    assert usd.total == D("47.00")
    assert usd.vat == D("6.48")
    assert ves.vat == D("1499.66")
    assert usd.base == D("40.52")
    assert ves.base == D("9372.84")
    assert a.cost_usd + b.cost_usd == D("33.75")


# ------------------------------------------------------------------ RN-06 (criterio 4)


def test_rn06_equivalente_de_15_usd() -> None:
    """RN-06: 15 × 231,0468 = 3.465,702 → Bs 3.465,70."""
    assert ves_equivalent(D("15"), Currency.USD, RATE) == D("3465.70")
    assert ves_equivalent(D("100.00"), Currency.VES, RATE) == D("100.00")


def test_rn06_criterio_4_vuelto_mixto() -> None:
    """Criterio 4: total Bs 2.890,00; paga 15 USD; recibe 2 USD y el resto en Bs → Bs 113,61."""
    paid = ves_equivalent(D("15"), Currency.USD, RATE)
    change = compute_change(D("2890.00"), paid, D("2"), RATE)
    assert change.total_ves == D("575.70")
    assert ves_equivalent(D("2"), Currency.USD, RATE) == D("462.09")
    assert change.rest_ves == D("113.61")


def test_rn06_vuelto_que_excede_se_rechaza() -> None:
    paid = ves_equivalent(D("15"), Currency.USD, RATE)
    with pytest.raises(ValueError):
        compute_change(D("2890.00"), paid, D("3"), RATE)


def test_rn06_sin_vuelto_si_falta_dinero() -> None:
    with pytest.raises(ValueError):
        compute_change(D("2890.00"), D("2000.00"), D("0"), RATE)


def test_rn06_referencia_usd_de_lo_que_falta() -> None:
    """RN-06: referencia USD = HU(falta_bs / tasa, 2). 2.890 / 231,0468 = 12,5083…"""
    assert usd_reference(D("2890.00"), RATE) == D("12.51")


# ------------------------------------------------------------------ RN-07 (criterio 6)


def test_rn07_criterio_6_deuda_en_usd() -> None:
    """Criterio 6: venta a fiado de Bs 2.890,00 a 231,0468 → deuda 12,51 USD."""
    assert credit_debt_usd(D("2890.00"), RATE) == D("12.51")


def test_rn07_criterio_6_abono_en_bs_y_saldo() -> None:
    """Criterio 6: con tasa 240,00 abona Bs 1.200,00 → 5,00 USD → saldo 7,51 USD."""
    debt = credit_debt_usd(D("2890.00"), RATE)
    payment = credit_payment_usd(D("1200.00"), Currency.VES, D("240.00"))
    assert payment == D("5.00")
    assert debt - payment == D("7.51")


def test_rn07_abono_en_usd_es_el_monto() -> None:
    assert credit_payment_usd(D("3.00"), Currency.USD, D("240.00")) == D("3.00")


# ------------------------------------------------------------------ RN-08 (criterio 2)


def test_rn08_criterio_2_costo_promedio() -> None:
    """Criterio 2: 7 u a 10,00 + 3 u a 12,00 → 10,6000 USD."""
    assert weighted_average_cost(D("7"), D("10.00"), D("3"), D("12.00")) == D("10.6000")


def test_rn08_existencia_cero_o_negativa_toma_costo_de_compra() -> None:
    assert weighted_average_cost(D("0"), D("10.00"), D("5"), D("13.00")) == D("13.0000")
    assert weighted_average_cost(D("-2"), D("10.00"), D("5"), D("13.00")) == D("13.0000")


def test_rn08_compra_del_caso_del_resumen_del_mes() -> None:
    """Plan Fase 5: 10 A a 10,00 + 5 A a 13,00 → 11,0000."""
    assert weighted_average_cost(D("10"), D("10.0000"), D("5"), D("13.00")) == D("11.0000")


def test_rn08_compra_por_empaque() -> None:
    """RN-08: 2 cajas de 12 bujías a 18,00 USD la caja → 24 u a 1,5000 USD."""
    p = pack_purchase(D("2"), D("12"), D("18.00"))
    assert p.qty == D("24")
    assert p.unit_cost == D("1.5000")


# ------------------------------------------------------------------ RN-11 (criterio 5)


def test_rn11_criterio_5_caja_cuadra() -> None:
    """Criterio 5: apertura 20 USD y Bs 500,00; entra 15 USD, salen 2 USD y Bs 113,61 → 33,00 USD y Bs 386,39."""
    assert expected_cash(D("20.00"), [D("15.00"), D("-2.00")]) == D("33.00")
    assert expected_cash(D("500.00"), [D("-113.61")]) == D("386.39")


def test_rn11_entradas_salidas_y_diferencia() -> None:
    expected = expected_cash(D("20.00"), [D("15.00")], cash_in=[D("5.00")], cash_out=[D("10.00")])
    assert expected == D("30.00")
    assert cash_difference(D("29.00"), expected) == D("-1.00")
