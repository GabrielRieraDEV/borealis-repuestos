import json
import sqlite3
from datetime import date
from decimal import Decimal as D

import pytest

from repuestos.db.connection import transaction
from repuestos.db.repositories import products as products_repo
from repuestos.domain.inventory import AdjustmentKind, MovementType
from repuestos.domain.pricing import pack_purchase
from repuestos.domain.products import ProductData, Unit
from repuestos.services import inventory_service, product_service, purchase_service
from repuestos.services.purchase_service import PurchaseLineInput as L
from repuestos.services.stock import apply_movement
from repuestos.tools import verify_stock
from tests.helpers import as_seller, pastillas

TODAY = date(2026, 11, 7)


@pytest.fixture
def supplier(conn: sqlite3.Connection, owner):
    return purchase_service.create_supplier(conn, owner, "Distribuidora Bolívar", "j-12345678-9", "0285-1111111")


def buy(conn, owner, supplier, *lines: tuple[int, str, str], **kw):
    return purchase_service.register_purchase(
        conn,
        owner,
        supplier.id,
        [L(pid, D(q), D(c)) for pid, q, c in lines],
        kw.pop("purchase_date", TODAY),
        today=TODAY,
        **kw,
    )


def stock_cost(conn, pid: int) -> tuple[D, D]:
    p = products_repo.get(conn, pid)
    return p.stock, p.data.cost_usd


def assert_invariant(conn) -> None:
    assert verify_stock.verify(conn) == []


# ------------------------------------------------------------------ registro


def test_criterio_2_compra_suma_y_promedia(conn, owner, supplier) -> None:
    """Criterio 2: existencia 7 a 10,00; se compran 3 a 12,00 → 10 unidades a 10,60."""
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10.00")), D("7"))
    purchase = buy(conn, owner, supplier, (p.id, "3", "12.00"), supplier_invoice="F-001")
    assert stock_cost(conn, p.id) == (D("10"), D("10.6000"))
    assert purchase.total_usd == D("36.00")
    assert purchase.items[0].line_total == D("36.00")
    mv = conn.execute(
        "SELECT type, qty_e3, stock_after_e3, unit_cost_usd_e4, purchase_id FROM inventory_movements ORDER BY id DESC"
    ).fetchone()
    assert tuple(mv) == ("PURCHASE", 3000, 10000, 106000, purchase.id)
    assert_invariant(conn)


def test_compra_por_empaque(conn, owner, supplier) -> None:
    """RN-08: 2 cajas de 12 bujías a 18,00 la caja → 24 u a 1,5000."""
    p = product_service.create_product(conn, owner, ProductData(name="Bujía NGK"))
    pack = pack_purchase(D("2"), D("12"), D("18.00"))
    buy(conn, owner, supplier, (p.id, str(pack.qty), str(pack.unit_cost)))
    assert stock_cost(conn, p.id) == (D("24"), D("1.5000"))
    assert_invariant(conn)


@pytest.mark.parametrize("initial", ["0", "-2"])
def test_existencia_cero_o_negativa_toma_costo_de_compra(conn, owner, supplier, initial: str) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10.00")), D("5"))
    with transaction(conn):  # deja la existencia en 0 o negativa con un movimiento válido
        apply_movement(conn, p.id, MovementType.ADJ_COUNT, D(initial) - D("5"), owner.id, reason="prueba")
    buy(conn, owner, supplier, (p.id, "4", "13.00"))
    assert stock_cost(conn, p.id) == (D(initial) + 4, D("13.0000"))
    assert_invariant(conn)


def test_mismo_producto_dos_veces_aplica_promedio_dos_veces(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10.00")), D("10"))
    buy(conn, owner, supplier, (p.id, "5", "13.00"), (p.id, "5", "16.00"))
    # (10×10 + 5×13)/15 = 11,0000; luego (15×11 + 5×16)/20 = 12,2500
    assert stock_cost(conn, p.id) == (D("20"), D("12.2500"))
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE type = 'PURCHASE'").fetchone()[0] == 2
    assert_invariant(conn)


def test_caso_resumen_del_mes_compra(conn, owner, supplier) -> None:
    """Plan Fase 5, paso 3: 10 A a 10,00 + compra 5 A a 13,00 → costo 11,0000; compras del mes 65,00."""
    a = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10.00")), D("10"))
    purchase = buy(conn, owner, supplier, (a.id, "5", "13.00"))
    assert purchase.total_usd == D("65.00")
    assert stock_cost(conn, a.id) == (D("15"), D("11.0000"))


def test_compra_con_fraccion(conn, owner, supplier) -> None:
    cable = product_service.create_product(
        conn, owner, ProductData(name="Cable", unit=Unit.METRO, allows_fraction=True, cost_usd=D("0.30")), D("100")
    )
    purchase = buy(conn, owner, supplier, (cable.id, "50.5", "0.3333"))
    assert purchase.total_usd == D("16.83")  # 50,5 × 0,3333 = 16,83165
    assert stock_cost(conn, cable.id)[0] == D("150.5")


def test_compra_audita_costos(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10.00")), D("7"))
    buy(conn, owner, supplier, (p.id, "3", "12.00"))
    details = json.loads(
        conn.execute("SELECT details_json FROM audit_log WHERE action = 'PURCHASE_CREATED'").fetchone()[0]
    )
    assert details["renglones"][0]["costo_antes"] == "10.0000"
    assert details["renglones"][0]["costo_despues"] == "10.6000"


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([], "al menos un producto"),
        ([("0", "1")], "mayor que cero"),
        ([("1", "-1")], "negativo"),
        ([("1", "1.00001")], "4 decimales"),
        ([("1.5", "1")], "unidades completas"),
    ],
)
def test_validaciones(conn, owner, supplier, lines, message) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    with pytest.raises(ValueError, match=message):
        buy(conn, owner, supplier, *[(p.id, q, c) for q, c in lines])
    assert conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 0


def test_fecha_futura_rechazada(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    with pytest.raises(ValueError, match="futura"):
        buy(conn, owner, supplier, (p.id, "1", "1"), purchase_date=date(2026, 11, 8))


def test_producto_inactivo_rechazado_y_nada_queda_a_medias(conn, owner, supplier) -> None:
    ok = product_service.create_product(conn, owner, pastillas(conn), D("1"))
    off = product_service.create_product(conn, owner, ProductData(name="Viejo"))
    product_service.set_active(conn, owner, off.id, False)
    with pytest.raises(ValueError, match="inactivo"):
        buy(conn, owner, supplier, (ok.id, "1", "1"), (off.id, "1", "1"))
    assert stock_cost(conn, ok.id)[0] == D("1")
    assert conn.execute("SELECT COUNT(*) FROM purchase_items").fetchone()[0] == 0


def test_vendedor_no_compra(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    with pytest.raises(PermissionError):
        purchase_service.register_purchase(conn, as_seller(owner), supplier.id, [L(p.id, D("1"), D("1"))], TODAY)
    with pytest.raises(PermissionError):
        purchase_service.list_purchases(conn, as_seller(owner))


def test_proveedor_duplicado(conn, owner, supplier) -> None:
    with pytest.raises(ValueError, match="Ya existe"):
        purchase_service.create_supplier(conn, owner, "distribuidora bolívar")


# ------------------------------------------------------------------ anulación (RF-31)


def test_anular_compra_resta_y_no_toca_costo(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10.00")), D("7"))
    purchase = buy(conn, owner, supplier, (p.id, "3", "12.00"))
    purchase_service.void_purchase(conn, owner, purchase.id, "Factura equivocada")
    assert stock_cost(conn, p.id) == (D("7"), D("10.6000"))  # el costo no se recalcula hacia atrás
    voided = purchase_service.get_purchase(conn, owner, purchase.id)
    assert voided.voided and voided.void_reason == "Factura equivocada"
    mv = conn.execute("SELECT type, qty_e3, purchase_id, reason FROM inventory_movements ORDER BY id DESC").fetchone()
    assert tuple(mv) == ("PURCHASE_VOID", -3000, purchase.id, "Factura equivocada")
    assert_invariant(conn)


def test_anular_bloqueada_si_deja_negativo(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    purchase = buy(conn, owner, supplier, (p.id, "5", "1"))
    inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("2"), "golpe")
    with pytest.raises(ValueError, match="quedaría con existencia -2"):
        purchase_service.void_purchase(conn, owner, purchase.id, "error")
    assert not purchase_service.get_purchase(conn, owner, purchase.id).voided
    assert stock_cost(conn, p.id)[0] == D("3")
    assert_invariant(conn)


def test_anular_suma_renglones_del_mismo_producto(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    purchase = buy(conn, owner, supplier, (p.id, "2", "1"), (p.id, "3", "1"))
    inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("1"), "x")
    with pytest.raises(ValueError):
        purchase_service.void_purchase(conn, owner, purchase.id, "error")


def test_anular_requiere_motivo_y_no_dos_veces(conn, owner, supplier) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    purchase = buy(conn, owner, supplier, (p.id, "5", "1"))
    with pytest.raises(ValueError, match="motivo"):
        purchase_service.void_purchase(conn, owner, purchase.id, "  ")
    purchase_service.void_purchase(conn, owner, purchase.id, "error")
    with pytest.raises(ValueError, match="ya está anulada"):
        purchase_service.void_purchase(conn, owner, purchase.id, "otra vez")
    with pytest.raises(PermissionError):
        purchase_service.void_purchase(conn, as_seller(owner), purchase.id, "x")


def test_lista_de_compras_con_filtros(conn, owner, supplier) -> None:
    a = product_service.create_product(conn, owner, pastillas(conn))
    b = product_service.create_product(conn, owner, ProductData(name="Cadena"))
    other = purchase_service.create_supplier(conn, owner, "Otro")
    buy(conn, owner, supplier, (a.id, "1", "1"), purchase_date=date(2026, 11, 1))
    buy(conn, owner, other, (b.id, "1", "1"), purchase_date=date(2026, 11, 5))
    ls = purchase_service.list_purchases
    assert len(ls(conn, owner)) == 2
    assert [p.supplier_name for p in ls(conn, owner, supplier_id=other.id)] == ["Otro"]
    assert len(ls(conn, owner, date_from=date(2026, 11, 2))) == 1
    assert len(ls(conn, owner, product_id=a.id)) == 1
