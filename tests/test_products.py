import json
import sqlite3
import time
from datetime import date
from decimal import Decimal as D

import pytest

from repuestos.db.connection import transaction
from repuestos.db.repositories import products as products_repo
from repuestos.domain.products import ProductData, Unit
from repuestos.domain.text import build_search_text, normalize
from repuestos.services import category_service, product_service, rate_service
from tests.helpers import as_seller, category_id, make_seller, pastillas


def _audit(conn: sqlite3.Connection, action: str) -> list[dict]:
    rows = conn.execute("SELECT details_json FROM audit_log WHERE action = ? ORDER BY id", (action,))
    return [json.loads(r[0]) for r in rows]


def test_normalize() -> None:
    assert normalize("Pastillas de FRENO — Bera 150") == "pastillas de freno bera 150"
    assert normalize("Tracción  ñandú, Último") == "traccion nandu ultimo"


# ------------------------------------------------------------------ alta


def test_create_assigns_sequential_codes(conn: sqlite3.Connection, owner) -> None:
    a = product_service.create_product(conn, owner, ProductData(name="Bujía"))
    b = product_service.create_product(conn, owner, ProductData(name="Cadena"))
    assert (a.code, b.code) == ("R-00001", "R-00002")
    assert conn.execute("SELECT next_number FROM doc_sequences WHERE doc_type = 'R'").fetchone()[0] == 3


def test_failed_create_does_not_consume_code(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, ProductData(name="A", barcode="123"))
    with pytest.raises(ValueError, match="código de barras"):
        product_service.create_product(conn, owner, ProductData(name="B", barcode="123"))
    c = product_service.create_product(conn, owner, ProductData(name="C"))
    assert c.code == "R-00002"


def test_initial_stock_creates_initial_movement_and_stock_matches(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("10"))
    assert p.stock == D("10")
    rows = conn.execute(
        "SELECT type, qty_e3, stock_after_e3, unit_cost_usd_e4, user_id FROM inventory_movements WHERE product_id = ?",
        (p.id,),
    ).fetchall()
    assert [tuple(r) for r in rows] == [("INITIAL", 10000, 10000, 70000, owner.id)]
    ledger = conn.execute("SELECT SUM(qty_e3) FROM inventory_movements WHERE product_id = ?", (p.id,)).fetchone()[0]
    assert conn.execute("SELECT stock_e3 FROM products WHERE id = ?", (p.id,)).fetchone()[0] == ledger
    assert conn.execute("SELECT cost_usd_e4 FROM products WHERE id = ?", (p.id,)).fetchone()[0] == 70000


def test_no_initial_stock_no_movement(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, ProductData(name="Bujía"))
    assert p.stock == 0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0


def test_fraction_rules(conn: sqlite3.Connection, owner) -> None:
    cable = ProductData(name="Cable eléctrico", unit=Unit.METRO, allows_fraction=True, cost_usd=D("0.30"))
    p = product_service.create_product(conn, owner, cable, initial_stock=D("100.5"))
    assert p.stock == D("100.500")
    with pytest.raises(ValueError, match="unidades completas"):
        product_service.create_product(conn, owner, ProductData(name="Bujía"), initial_stock=D("2.5"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"name": "  "}, "nombre"),
        ({"price_usd": D("-1")}, "negativo"),
        ({"price_usd": D("1.23456")}, "4 decimales"),
        ({"category_id": 999}, "categoría"),
    ],
)
def test_create_validation(conn: sqlite3.Connection, owner, change: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        product_service.create_product(conn, owner, pastillas(conn, **change))


def test_create_is_audited(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("4"))
    (details,) = _audit(conn, "PRODUCT_CREATED")
    assert details["codigo"] == "R-00001"
    assert details["existencia_inicial"] == "4"
    assert details["precio_usd"] == "12.5000"


# ------------------------------------------------------------------ permisos


def test_seller_cannot_create_or_edit_or_change_price(conn: sqlite3.Connection, owner) -> None:
    seller = make_seller(conn, owner)
    p = product_service.create_product(conn, owner, pastillas(conn))
    with pytest.raises(PermissionError):
        product_service.create_product(conn, seller, ProductData(name="X"))
    with pytest.raises(PermissionError):
        product_service.update_product(conn, seller, p.id, pastillas(conn, price_usd=D("1.00")))
    with pytest.raises(PermissionError):
        product_service.set_active(conn, seller, p.id, False)
    with pytest.raises(PermissionError):
        product_service.get_product(conn, seller, p.id)
    assert products_repo.get(conn, p.id).data.price_usd == D("12.50")


def test_seller_never_receives_cost(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    seller = as_seller(owner)
    assert product_service.search(conn, seller, "bera")[0].cost_usd is None
    assert product_service.get_view(conn, seller, p.id).cost_usd is None
    assert product_service.search(conn, owner, "bera")[0].cost_usd == D("7.00")


# ------------------------------------------------------------------ edición


def test_price_and_cost_change_audited_before_after(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    product_service.update_product(conn, owner, p.id, pastillas(conn, price_usd=D("13.00"), cost_usd=D("7.50")))
    assert _audit(conn, "PRICE_CHANGE") == [{"codigo": "R-00001", "antes": "12.5000", "despues": "13.0000"}]
    assert _audit(conn, "COST_CHANGE") == [{"codigo": "R-00001", "antes": "7.0000", "despues": "7.5000"}]
    assert _audit(conn, "PRODUCT_UPDATED") == []


def test_edit_does_not_touch_stock_or_code(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("5"))
    q = product_service.update_product(conn, owner, p.id, pastillas(conn, name="Pastillas traseras"))
    assert (q.code, q.stock) == (p.code, D("5"))
    assert _audit(conn, "PRODUCT_UPDATED")[0]["name"]["despues"] == "Pastillas traseras"


def test_deactivate_hides_from_search(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    product_service.set_active(conn, owner, p.id, False)
    assert product_service.search(conn, owner, "bera") == []
    assert [v.id for v in product_service.search(conn, owner, "bera", include_inactive=True)] == [p.id]
    assert product_service.search(conn, as_seller(owner), "bera", include_inactive=True) == []
    assert _audit(conn, "PRODUCT_DEACTIVATED") == [{"codigo": "R-00001"}]


# ------------------------------------------------------------------ búsqueda (RF-12)


def test_search_example_from_prd(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    product_service.create_product(conn, owner, ProductData(name="Pastillas de freno traseras — Owen 150"))
    product_service.create_product(conn, owner, ProductData(name="Bujía", compatible_models="Bera 150"))
    results = product_service.search(conn, owner, "pastilla bera 150")
    assert [r.id for r in results] == [p.id]


@pytest.mark.parametrize("query", ["BERA pastilla", "150 freno", "frenos genérica", "genérica", "r-00001"])
def test_search_any_order_case_and_accents(conn: sqlite3.Connection, owner, query: str) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    assert p.id in [r.id for r in product_service.search(conn, owner, query)]


def test_search_includes_category_name(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    assert [r.id for r in product_service.search(conn, owner, "frenos")] == [p.id]


def test_barcode_exact_has_priority(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, ProductData(name="Calcomanía 7591234 genérica"))
    target = product_service.create_product(conn, owner, ProductData(name="Zapata", barcode="7591234"))
    results = product_service.search(conn, owner, "7591234")
    assert results[0].id == target.id
    assert len(results) == 2
    assert product_service.find_by_scan(conn, owner, "7591234").id == target.id
    assert product_service.find_by_scan(conn, owner, "R-00002").id == target.id
    assert product_service.find_by_scan(conn, owner, "000") is None


def test_search_shows_price_in_bs_with_current_rate(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn))
    assert product_service.search(conn, owner, "bera")[0].price_ves is None
    rate_service.set_manual_rate(conn, owner, D("231.0468"), today=date(2026, 11, 7))
    view = product_service.search(conn, owner, "bera", today=date(2026, 11, 7))[0]
    assert view.price_ves == D("2890.00")


def test_search_like_wildcards_are_literal(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, ProductData(name="Aceite"))
    # la normalización deja solo letras y números: '%' y '_' nunca llegan a LIKE como comodines
    assert len(product_service.search(conn, owner, "%")) == 1  # búsqueda vacía: lista todo
    assert product_service.search(conn, owner, "x%z") == []


def test_low_stock_flag_and_count(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("9"))
    product_service.create_product(conn, owner, ProductData(name="Cadena", min_stock=D("10")), initial_stock=D("11"))
    product_service.create_product(conn, owner, ProductData(name="Sin alerta", min_stock=D("0")))
    assert product_service.search(conn, owner, "bera")[0].is_low  # criterio 7
    assert product_service.count_low_stock(conn) == 1


def test_rename_category_updates_search_text(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    category_service.rename_category(conn, owner, category_id(conn, "Frenos"), "Sistema de frenado")
    assert [r.id for r in product_service.search(conn, owner, "frenado")] == [p.id]


def test_search_performance_5000_products(conn: sqlite3.Connection, owner) -> None:
    """RF-12 / RNF-05: menos de 300 ms con 5.000 productos."""
    brands = ["Genérica", "NGK", "Bera", "Empire", "Yamaha", "Suzuki"]
    models = ["Bera 150", "Owen 150", "Horse 150", "Speed 200", "Jaguar 150", "GN 125"]
    parts = ["Pastillas de freno", "Bujía", "Cadena", "Piñón", "Corona", "Filtro de aceite", "Guaya", "Bombillo"]
    cats = [c.id for c in category_service.list_categories(conn)]
    with transaction(conn):
        for i in range(5000):
            data = ProductData(
                name=f"{parts[i % len(parts)]} {i}",
                brand=brands[i % len(brands)],
                compatible_models=models[i % len(models)],
                category_id=cats[i % len(cats)],
                price_usd=D("1.00"),
            )
            code = products_repo.next_code(conn)
            products_repo.insert(
                conn, code, data, build_search_text([data.name, data.brand, data.compatible_models, code])
            )
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    worst = 0.0
    for q in ["pastilla bera 150", "bujia", "cadena horse", "R-04999", "filtro aceite gn", "zzz", ""]:
        t0 = time.perf_counter()
        product_service.search(conn, owner, q)
        worst = max(worst, time.perf_counter() - t0)
    assert worst < 0.300, f"la búsqueda más lenta tardó {worst * 1000:.0f} ms"
