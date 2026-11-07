import ast
import json
import re
import sqlite3
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from repuestos.db.repositories import products as products_repo
from repuestos.domain.inventory import AdjustmentKind
from repuestos.domain.products import ProductData, Unit
from repuestos.services import inventory_service, product_service, purchase_service
from repuestos.services.inventory_service import CountEntry
from repuestos.services.purchase_service import PurchaseLineInput
from repuestos.tools import verify_stock
from tests.helpers import as_seller, category_id, pastillas

TODAY = date(2026, 11, 7)


def assert_invariant(conn: sqlite3.Connection) -> None:
    assert verify_stock.verify(conn) == []


def stock(conn, pid: int) -> D:
    return products_repo.get(conn, pid).stock


# ------------------------------------------------------------------ ajustes (RF-41)


@pytest.mark.parametrize(
    ("kind", "expected", "mtype", "qty_e3"),
    [
        (AdjustmentKind.DAMAGE, "8", "ADJ_DAMAGE", -2000),
        (AdjustmentKind.MISSING, "8", "ADJ_MISSING", -2000),
        (AdjustmentKind.INTERNAL_USE, "8", "ADJ_INTERNAL_USE", -2000),
        (AdjustmentKind.CORRECTION_IN, "12", "ADJ_CORRECTION_IN", 2000),
    ],
)
def test_ajustes(conn, owner, kind, expected, mtype, qty_e3) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("7.00")), D("10"))
    result = inventory_service.adjust(conn, owner, p.id, kind, D("2"), "motivo")
    assert stock(conn, p.id) == D(expected)
    assert result.stock_after == D(expected)
    mv = conn.execute(
        "SELECT type, qty_e3, unit_cost_usd_e4, reason FROM inventory_movements ORDER BY id DESC"
    ).fetchone()
    assert tuple(mv) == (mtype, qty_e3, 70000, "motivo")  # guarda el costo promedio del momento (RN-13)
    assert_invariant(conn)


def test_caso_resumen_ajuste_cable(conn, owner) -> None:
    """Plan Fase 5, paso 5: 2 m de B dañados a 0,30 → pérdida 0,60 USD (valorizable desde el movimiento)."""
    b = product_service.create_product(
        conn, owner, ProductData(name="Cable", unit=Unit.METRO, allows_fraction=True, cost_usd=D("0.30")), D("100")
    )
    inventory_service.adjust(conn, owner, b.id, AdjustmentKind.DAMAGE, D("2"), "dañado")
    qty, cost = conn.execute(
        "SELECT qty_e3, unit_cost_usd_e4 FROM inventory_movements WHERE type = 'ADJ_DAMAGE'"
    ).fetchone()
    assert D(abs(qty)) / 1000 * D(cost) / 10000 == D("0.6")
    assert stock(conn, b.id) == D("98")


def test_ajuste_validaciones(conn, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn), D("1"))
    with pytest.raises(ValueError, match="motivo"):
        inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("1"), " ")
    with pytest.raises(ValueError, match="mayor que cero"):
        inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("0"), "x")
    with pytest.raises(ValueError, match="unidades completas"):
        inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("0.5"), "x")
    with pytest.raises(ValueError, match="conteo físico"):
        inventory_service.adjust(conn, owner, p.id, AdjustmentKind.MISSING, D("2"), "x")
    with pytest.raises(PermissionError):
        inventory_service.adjust(conn, as_seller(owner), p.id, AdjustmentKind.DAMAGE, D("1"), "x")
    assert stock(conn, p.id) == D("1")
    assert_invariant(conn)


def test_ajuste_auditado(conn, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("7")), D("10"))
    inventory_service.adjust(conn, owner, p.id, AdjustmentKind.INTERNAL_USE, D("1"), "para la moto del local")
    d = json.loads(conn.execute("SELECT details_json FROM audit_log WHERE action = 'ADJUSTMENT'").fetchone()[0])
    assert d == {
        "codigo": "R-00001",
        "tipo": "INTERNAL_USE",
        "cantidad": "-1",
        "existencia_antes": "10.000",
        "existencia_despues": "9.000",
        "costo_usd": "7.0000",
        "motivo": "para la moto del local",
    }


# ------------------------------------------------------------------ conteo (RF-42)


def test_conteo_diferencia_positiva_negativa_y_cero(conn, owner) -> None:
    a = product_service.create_product(conn, owner, pastillas(conn), D("10"))
    b = product_service.create_product(conn, owner, ProductData(name="Cadena"), D("5"))
    c = product_service.create_product(conn, owner, ProductData(name="Piñón"), D("3"))
    results = inventory_service.register_count(
        conn, owner, [CountEntry(a.id, D("12")), CountEntry(b.id, D("4")), CountEntry(c.id, D("3"))], "estante A"
    )
    assert [(r.code, r.difference) for r in results] == [("R-00001", 2), ("R-00002", -1), ("R-00003", 0)]
    assert (stock(conn, a.id), stock(conn, b.id), stock(conn, c.id)) == (D("12"), D("4"), D("3"))
    rows = conn.execute("SELECT product_id, qty_e3, reason FROM inventory_movements WHERE type = 'ADJ_COUNT'")
    assert [tuple(r) for r in rows] == [
        (a.id, 2000, "Conteo físico: estante A"),
        (b.id, -1000, "Conteo físico: estante A"),
    ]
    d = json.loads(conn.execute("SELECT details_json FROM audit_log WHERE action = 'STOCK_COUNT'").fetchone()[0])
    assert d["productos_contados"] == 3 and len(d["diferencias"]) == 2
    assert_invariant(conn)


def test_conteo_a_cero_y_fraccion(conn, owner) -> None:
    cable = product_service.create_product(
        conn, owner, ProductData(name="Cable", unit=Unit.METRO, allows_fraction=True), D("10")
    )
    inventory_service.register_count(conn, owner, [CountEntry(cable.id, D("7.25"))])
    assert stock(conn, cable.id) == D("7.25")
    inventory_service.register_count(conn, owner, [CountEntry(cable.id, D("0"))])
    assert stock(conn, cable.id) == 0
    assert_invariant(conn)


def test_conteo_es_todo_o_nada(conn, owner) -> None:
    a = product_service.create_product(conn, owner, pastillas(conn), D("10"))
    b = product_service.create_product(conn, owner, ProductData(name="Cadena"), D("5"))
    with pytest.raises(ValueError, match="R-00002"):
        inventory_service.register_count(conn, owner, [CountEntry(a.id, D("12")), CountEntry(b.id, D("1.5"))])
    assert stock(conn, a.id) == D("10")
    with pytest.raises(ValueError, match="negativo"):
        inventory_service.register_count(conn, owner, [CountEntry(a.id, D("-1"))])
    with pytest.raises(ValueError, match="dos veces"):
        inventory_service.register_count(conn, owner, [CountEntry(a.id, D("1")), CountEntry(a.id, D("2"))])
    with pytest.raises(PermissionError):
        inventory_service.register_count(conn, as_seller(owner), [CountEntry(a.id, D("1"))])


def test_productos_para_contar_por_categoria_estante_y_busqueda(conn, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn, location="A-3"))
    product_service.create_product(conn, owner, ProductData(name="Bujía", location="B-1"))
    product_service.create_product(conn, owner, ProductData(name="Cadena", location="A-3"))
    names = lambda rows: [r.name for r in rows]  # noqa: E731
    assert names(inventory_service.products_for_count(conn, owner, category_id=category_id(conn, "Frenos"))) == [
        "Pastillas de freno delanteras — Bera 150"
    ]
    assert names(inventory_service.products_for_count(conn, owner, location="a-3")) == [
        "Cadena",
        "Pastillas de freno delanteras — Bera 150",
    ]
    assert names(inventory_service.products_for_count(conn, owner, query="buj")) == ["Bujía"]
    assert inventory_service.locations(conn) == ["A-3", "B-1"]


# ------------------------------------------------------------------ kardex e historial (RF-16)


def test_kardex_e_historial(conn, owner) -> None:
    sup = purchase_service.create_supplier(conn, owner, "Distribuidora")
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10")), D("7"))
    purchase_service.register_purchase(
        conn, owner, sup.id, [PurchaseLineInput(p.id, D("3"), D("12"))], TODAY, "F-9", today=TODAY
    )
    inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("1"), "golpe")
    k = inventory_service.kardex(conn, owner, p.id)
    assert [(line.kind.value, line.qty, line.stock_after) for line in k] == [
        ("ADJ_DAMAGE", D("-1"), D("9")),
        ("PURCHASE", D("3"), D("10")),
        ("INITIAL", D("7"), D("7")),
    ]
    assert k[1].supplier_invoice == "F-9" and k[1].supplier_name == "Distribuidora"
    assert k[0].user_name == "Yoleida Romero"
    h = inventory_service.purchase_history(conn, owner, p.id)
    assert [(x.supplier_name, x.supplier_invoice, x.qty, x.unit_cost) for x in h] == [
        ("Distribuidora", "F-9", D("3"), D("12"))
    ]
    with pytest.raises(PermissionError):
        inventory_service.kardex(conn, as_seller(owner), p.id)


# ------------------------------------------------------------------ para pedir (RF-43, RN-10, criterio 7)


def test_para_pedir_criterio_7_y_ultima_compra(conn, owner) -> None:
    sup1 = purchase_service.create_supplier(conn, owner, "Viejo")
    sup2 = purchase_service.create_supplier(conn, owner, "Nuevo")
    a = product_service.create_product(conn, owner, pastillas(conn, min_stock=D("10")), D("0"))
    b = product_service.create_product(conn, owner, ProductData(name="Cadena", min_stock=D("10")), D("11"))
    c = product_service.create_product(conn, owner, ProductData(name="Sin mínimo", min_stock=D("0")))
    d = product_service.create_product(conn, owner, ProductData(name="Inactivo", min_stock=D("10")))
    product_service.set_active(conn, owner, d.id, False)
    L = PurchaseLineInput
    purchase_service.register_purchase(conn, owner, sup1.id, [L(a.id, D("4"), D("6"))], date(2026, 11, 1), today=TODAY)
    p2 = purchase_service.register_purchase(
        conn, owner, sup2.id, [L(a.id, D("5"), D("7.5"))], date(2026, 11, 5), today=TODAY
    )
    p3 = purchase_service.register_purchase(
        conn, owner, sup1.id, [L(a.id, D("1"), D("99"))], date(2026, 11, 6), today=TODAY
    )
    purchase_service.void_purchase(conn, owner, p3.id, "error")  # anulada: no cuenta como última compra
    assert stock(conn, a.id) == D("9")  # criterio 7: mínimo 10, existencia 9
    rows = inventory_service.to_order(conn, owner)
    assert [r.product_id for r in rows] == [a.id]
    assert (rows[0].last_supplier, rows[0].last_cost, rows[0].category_name) == ("Nuevo", D("7.5"), "Frenos")
    assert p2.id and b.id and c.id
    with pytest.raises(PermissionError):
        inventory_service.to_order(conn, as_seller(owner))


def test_para_pedir_agrupado_por_categoria(conn, owner) -> None:
    product_service.create_product(conn, owner, ProductData(name="Zeta", category_id=category_id(conn, "Motor")))
    product_service.create_product(conn, owner, ProductData(name="Alfa", category_id=category_id(conn, "Frenos")))
    product_service.create_product(conn, owner, ProductData(name="Sin cat"))
    rows = inventory_service.to_order(conn, owner)
    assert [(r.category_name, r.name) for r in rows] == [("Frenos", "Alfa"), ("Motor", "Zeta"), ("", "Sin cat")]


# ------------------------------------------------------------------ ningún float


SRC = Path(__file__).resolve().parents[1] / "src" / "repuestos"


def test_ningun_float_en_el_codigo() -> None:
    """Ningún uso de ``float`` en el código: ni anotaciones, ni llamadas, ni literales con decimales."""
    hits = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Name) and node.id == "float") or (
                isinstance(node, ast.Constant) and isinstance(node.value, float)
            ):
                hits.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    assert hits == []


def test_columnas_escaladas_son_enteros(conn, owner) -> None:
    sup = purchase_service.create_supplier(conn, owner, "S")
    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("7.1234")), D("2.000"))
    purchase_service.register_purchase(
        conn, owner, sup.id, [PurchaseLineInput(p.id, D("3"), D("1.3333"))], TODAY, today=TODAY
    )
    inventory_service.register_count(conn, owner, [CountEntry(p.id, D("4"))])
    for table in ("products", "inventory_movements", "purchases", "purchase_items"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if re.search(r"_(e\d|bp)$", r[1])]
        for col in cols:
            types = {r[0] for r in conn.execute(f"SELECT DISTINCT typeof({col}) FROM {table}")}
            assert types <= {"integer", "null"}, f"{table}.{col}: {types}"
