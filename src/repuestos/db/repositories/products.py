"""Repositorio de productos. Conversión entero <-> Decimal solo aquí."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from repuestos.domain.money import from_db, to_db
from repuestos.domain.products import Product, ProductData, Unit

_SELECT = """
SELECT p.*, COALESCE(c.name, '') AS category_name
FROM products p LEFT JOIN categories c ON c.id = p.category_id
"""


def _to_product(r: sqlite3.Row) -> Product:
    data = ProductData(
        name=r["name"],
        brand=r["brand"],
        compatible_models=r["compatible_models"],
        category_id=r["category_id"],
        location=r["location"],
        unit=Unit(r["unit"]),
        allows_fraction=bool(r["allows_fraction"]),
        barcode=r["barcode"],
        price_usd=from_db(r["price_usd_e4"], "e4"),
        cost_usd=from_db(r["cost_usd_e4"], "e4"),
        min_stock=from_db(r["min_stock_e3"], "e3"),
    )
    return Product(
        id=r["id"],
        code=r["code"],
        data=data,
        category_name=r["category_name"],
        stock=from_db(r["stock_e3"], "e3"),
        active=bool(r["active"]),
    )


def next_code(conn: sqlite3.Connection) -> str:
    """Código propio R-00001 desde doc_sequences('R'), dentro de la transacción del alta (sin saltos)."""
    row = conn.execute(
        "UPDATE doc_sequences SET next_number = next_number + 1 WHERE doc_type = 'R' RETURNING next_number - 1"
    ).fetchone()
    return f"R-{row[0]:05d}"


def _data_params(data: ProductData, search_text: str) -> dict[str, object]:
    return {
        "barcode": data.barcode,
        "name": data.name,
        "brand": data.brand,
        "compatible_models": data.compatible_models,
        "category_id": data.category_id,
        "location": data.location,
        "unit": data.unit.value,
        "allows_fraction": int(data.allows_fraction),
        "cost_usd_e4": to_db(data.cost_usd, "e4"),
        "price_usd_e4": to_db(data.price_usd, "e4"),
        "min_stock_e3": to_db(data.min_stock, "e3"),
        "search_text": search_text,
    }


def insert(conn: sqlite3.Connection, code: str, data: ProductData, search_text: str) -> int:
    params = _data_params(data, search_text) | {"code": code}
    cols = ", ".join(params)
    marks = ", ".join(f":{k}" for k in params)
    cur = conn.execute(f"INSERT INTO products ({cols}) VALUES ({marks})", params)
    return int(cur.lastrowid)  # type: ignore[arg-type]


def update(conn: sqlite3.Connection, product_id: int, data: ProductData, search_text: str) -> None:
    params = _data_params(data, search_text)
    sets = ", ".join(f"{k} = :{k}" for k in params)
    conn.execute(
        f"UPDATE products SET {sets}, updated_at = datetime('now', 'localtime') WHERE id = :id",
        params | {"id": product_id},
    )


def set_search_text(conn: sqlite3.Connection, product_id: int, search_text: str) -> None:
    conn.execute("UPDATE products SET search_text = ? WHERE id = ?", (search_text, product_id))


def set_active(conn: sqlite3.Connection, product_id: int, active: bool) -> None:
    conn.execute(
        "UPDATE products SET active = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (int(active), product_id),
    )


def set_stock(conn: sqlite3.Connection, product_id: int, stock: Decimal) -> None:
    conn.execute("UPDATE products SET stock_e3 = ? WHERE id = ?", (to_db(stock, "e3"), product_id))


def get(conn: sqlite3.Connection, product_id: int) -> Product | None:
    r = conn.execute(_SELECT + " WHERE p.id = ?", (product_id,)).fetchone()
    return _to_product(r) if r else None


def get_stock(conn: sqlite3.Connection, product_id: int) -> Decimal:
    return from_db(conn.execute("SELECT stock_e3 FROM products WHERE id = ?", (product_id,)).fetchone()[0], "e3")


def barcode_owner(conn: sqlite3.Connection, barcode: str) -> tuple[int, str, str] | None:
    r = conn.execute("SELECT id, code, name FROM products WHERE barcode = ?", (barcode,)).fetchone()
    return (r["id"], r["code"], r["name"]) if r else None


def ids_in_category(conn: sqlite3.Connection, category_id: int) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM products WHERE category_id = ?", (category_id,))]


def _like(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(
    conn: sqlite3.Connection,
    words: list[str],
    exact: str | None,
    include_inactive: bool,
    limit: int,
) -> list[Product]:
    """RF-12: cada palabra debe aparecer en search_text (AND), en cualquier orden.

    Si ``exact`` coincide con un código de barras o un código propio, ese producto sale primero.
    """
    where: list[str] = []
    params: list[object] = []
    for w in words:
        where.append("p.search_text LIKE ? ESCAPE '\\'")
        params.append(_like(w))
    if not include_inactive:
        where.append("p.active = 1")
    order = "p.name COLLATE NOCASE, p.id"
    order_params: list[object] = []
    if exact:
        order = "CASE WHEN p.barcode = ? OR p.code = ? COLLATE NOCASE THEN 0 ELSE 1 END, " + order
        order_params = [exact, exact]
    sql = _SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order} LIMIT ?"
    rows = conn.execute(sql, [*params, *order_params, limit]).fetchall()
    return [_to_product(r) for r in rows]


def find_exact(conn: sqlite3.Connection, text: str, include_inactive: bool = False) -> Product | None:
    """Código de barras o código propio exacto (lo que escribe el lector)."""
    sql = _SELECT + " WHERE (p.barcode = ? OR p.code = ? COLLATE NOCASE)"
    if not include_inactive:
        sql += " AND p.active = 1"
    r = conn.execute(sql + " ORDER BY p.barcode = ? DESC LIMIT 1", (text, text, text)).fetchone()
    return _to_product(r) if r else None


def count_low_stock(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM products WHERE active = 1 AND min_stock_e3 > 0 AND stock_e3 <= min_stock_e3"
    ).fetchone()[0]
