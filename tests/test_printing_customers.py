import sqlite3
from decimal import Decimal as D

import pytest

from repuestos.domain.sale import PaymentInput as P
from repuestos.domain.sale import PaymentMethod as M
from repuestos.printing import printer
from repuestos.printing.ticket import WIDTH
from repuestos.services import (
    cash_service,
    customer_service,
    print_service,
    product_service,
    rate_service,
    sale_service,
)
from repuestos.services.sale_service import CartItem
from tests.helpers import make_seller, pastillas

RATE = D("231.0468")


@pytest.fixture
def sale(conn: sqlite3.Connection, owner):
    rate_service.set_manual_rate(conn, owner, RATE)
    a = product_service.create_product(conn, owner, pastillas(conn), D("10"))
    cash_service.open_session(conn, owner, D("20"), D("500"))
    customer = customer_service.create(conn, owner, "José Pérez", "V-12.345.678")
    return sale_service.charge(
        conn, owner, [CartItem(a.id, D("1"))], [P(M.CASH_USD, D("15"))], RATE, customer.id, change_usd=D("2")
    )


# ------------------------------------------------------------------ nota de entrega (RN-12)


def test_ticket_de_venta(conn, owner, sale) -> None:
    lines = print_service.sale_lines(conn, owner, sale.id)
    text = "\n".join(lines)
    assert all(len(line) <= WIDTH for line in lines)
    for expected in [
        "PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P.",
        "RIF V-31463591-0",
        "NOTA DE ENTREGA - NO VALIDA COMO FACTURA",
        "Nro: NE-000001",
        "Vendedor: Yoleida Romero",
        "Cliente: José Pérez",
        "C.I./RIF: V-12345678",
        "Pastillas de freno delanteras - Bera 150",  # sin el guion largo que la impresora no tiene
        "1 x 2.890,00",
    ]:
        assert expected in text, expected
    assert any(line.startswith("Base imponible") and line.endswith("Bs 2.491,38") for line in lines)
    assert any(line.startswith("IVA 16%") and line.endswith("Bs 398,62") for line in lines)
    assert any(line.startswith("TOTAL") and line.endswith("Bs 2.890,00") for line in lines)
    assert any(line.startswith("Referencia") and line.endswith("USD 12,50") for line in lines)
    assert any(line.startswith("Tasa BCV") and line.endswith("231,0468") for line in lines)
    assert any("Efectivo USD 15,00" in line and line.endswith("Bs 3.465,70") for line in lines)
    assert any("Vuelto USD" in line and line.endswith("USD 2,00") for line in lines)
    assert any("Vuelto Bs" in line and line.endswith("Bs 113,61") for line in lines)
    assert "—" not in text


def test_ticket_anulado_y_reimpresion(conn, owner, sale) -> None:
    assert "(reimpresión)" in "\n".join(print_service.sale_lines(conn, owner, sale.id, reprint=True))
    sale_service.void_sale(conn, owner, sale.id, "error")
    assert "*** ANULADA ***" in "\n".join(print_service.sale_lines(conn, owner, sale.id, reprint=True))


def test_sin_impresora_lanza_print_error_y_la_venta_queda(conn, owner, sale) -> None:
    with pytest.raises(print_service.PrintError, match="No hay impresora"):
        print_service.print_sale(conn, owner, sale.id)
    assert sale_service.get_sale(conn, owner, sale.id).status == "COMPLETED"


def test_impresora_inexistente(conn, owner, sale) -> None:
    with pytest.raises(printer.PrintError, match="no respondió"):
        printer.send_to_printer("Impresora que no existe 123", ["hola"])


def test_guardar_pdf(conn, owner, sale, tmp_path) -> None:
    path = print_service.save_sale_pdf(conn, owner, sale.id, tmp_path)
    assert path.name == "NE-000001.pdf"
    assert path.read_bytes().startswith(b"%PDF")


# ------------------------------------------------------------------ ticket de cierre


def test_ticket_de_cierre_ciego(conn, owner, sale) -> None:
    session_id = sale.session_id
    cash_service.close_session(conn, owner, D("33"), D("380"))
    owner_text = "\n".join(print_service.close_lines(conn, owner, session_id))
    assert "CIERRE DE CAJA" in owner_text and "Esperado USD" in owner_text
    assert "Diferencia Bs" in owner_text and "Bs -6,39" in owner_text
    seller = make_seller(conn, owner)
    seller_text = "\n".join(print_service.close_lines(conn, seller, session_id))
    assert "Contado USD" in seller_text
    assert "Esperado" not in seller_text and "Diferencia" not in seller_text


# ------------------------------------------------------------------ clientes (RF-51)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("V-12.345.678", "V12345678"),
        ("12345678", "V12345678"),
        ("e 8123456", "E8123456"),
        ("J-12345678-9", "J123456789"),
    ],
)
def test_normalizar_documento(text, expected) -> None:
    assert customer_service.normalize_id_doc(text) == expected


@pytest.mark.parametrize("text", ["", "X123456", "V12", "abc"])
def test_documento_invalido(text) -> None:
    with pytest.raises(ValueError):
        customer_service.normalize_id_doc(text)


def test_crear_y_buscar_cliente(conn, owner) -> None:
    seller = make_seller(conn, owner)
    c = customer_service.create(conn, seller, "  María   González ", "v14555666", "0414-0000000")
    assert (c.name, c.id_doc, c.credit_enabled) == ("María González", "V14555666", False)
    assert customer_service.search(conn, "14.555.666")[0].id == c.id
    assert customer_service.search(conn, "gonz")[0].id == c.id
    assert customer_service.search(conn, "Consumidor") == []  # el consumidor final no se busca
    with pytest.raises(ValueError, match="Ya existe"):
        customer_service.create(conn, owner, "Otra", "V-14555666")
    assert customer_service.final_consumer(conn).name == "Consumidor final"
