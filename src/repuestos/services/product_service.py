"""Productos (RF-10 a RF-15): alta con código R-00001, edición, desactivación, existencia inicial y búsqueda."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import categories as categories_repo
from repuestos.db.repositories import inventory as inventory_repo
from repuestos.db.repositories import products as repo
from repuestos.domain.inventory import MovementType
from repuestos.domain.pricing import check_quantity, unit_price_ves
from repuestos.domain.products import Product, ProductData, clean_product_data
from repuestos.domain.text import build_search_text, search_words
from repuestos.domain.users import User, require_owner
from repuestos.services import rate_service, settings_service
from repuestos.services.audit_service import audit

SEARCH_LIMIT = 200


@dataclass(frozen=True, slots=True)
class ProductView:
    """Lo que se muestra en la búsqueda (RF-12). ``cost_usd`` es None para el vendedor."""

    id: int
    code: str
    barcode: str | None
    name: str
    brand: str
    compatible_models: str
    category_name: str
    location: str
    unit: str
    allows_fraction: bool
    stock: Decimal
    min_stock: Decimal
    price_usd: Decimal
    price_ves: Decimal | None  # None si no hay tasa
    cost_usd: Decimal | None
    active: bool
    is_low: bool


def _search_text(conn: sqlite3.Connection, code: str, data: ProductData) -> str:
    category = categories_repo.get(conn, data.category_id) if data.category_id else None
    return build_search_text(
        [data.name, data.brand, data.compatible_models, category.name if category else "", code, data.barcode]
    )


def _check_category(conn: sqlite3.Connection, data: ProductData) -> None:
    if data.category_id is not None and categories_repo.get(conn, data.category_id) is None:
        raise ValueError("La categoría elegida no existe.")


def _check_barcode(conn: sqlite3.Connection, data: ProductData, product_id: int | None) -> None:
    if not data.barcode:
        return
    owner = repo.barcode_owner(conn, data.barcode)
    if owner and owner[0] != product_id:
        raise ValueError(f"Ese código de barras ya está en el producto {owner[1]} — {owner[2]}.")


def _to_view(p: Product, user: User, rate: Decimal | None, multiple: Decimal) -> ProductView:
    d = p.data
    return ProductView(
        id=p.id,
        code=p.code,
        barcode=d.barcode,
        name=d.name,
        brand=d.brand,
        compatible_models=d.compatible_models,
        category_name=p.category_name,
        location=d.location,
        unit=d.unit.value,
        allows_fraction=d.allows_fraction,
        stock=p.stock,
        min_stock=d.min_stock,
        price_usd=d.price_usd,
        price_ves=unit_price_ves(d.price_usd, rate, multiple) if rate is not None else None,
        cost_usd=d.cost_usd if user.is_owner else None,
        active=p.active,
        is_low=p.is_low,
    )


# ------------------------------------------------------------------ alta


def create_product(
    conn: sqlite3.Connection,
    user: User,
    data: ProductData,
    initial_stock: Decimal = Decimal("0"),
) -> Product:
    """RF-10/RF-11: alta con código propio y, si hay existencia inicial, movimiento INITIAL con su costo (RN-08).

    Una sola transacción: products, doc_sequences('R'), inventory_movements(INITIAL), audit_log.
    """
    require_owner(user, "crear productos")
    data = clean_product_data(data)
    if initial_stock < 0:
        raise ValueError("La existencia inicial no puede ser negativa.")
    if initial_stock > 0:
        check_quantity(initial_stock, data.allows_fraction)
    with transaction(conn):
        _check_category(conn, data)
        _check_barcode(conn, data, None)
        code = repo.next_code(conn)
        product_id = repo.insert(conn, code, data, _search_text(conn, code, data))
        if initial_stock > 0:
            inventory_repo.insert_movement(
                conn,
                product_id,
                MovementType.INITIAL,
                initial_stock,
                initial_stock,
                data.cost_usd,
                user.id,
                reason="Existencia inicial",
            )
            repo.set_stock(conn, product_id, initial_stock)
        audit(
            conn,
            user.id,
            "PRODUCT_CREATED",
            "product",
            product_id,
            {
                "codigo": code,
                "nombre": data.name,
                "precio_usd": data.price_usd,
                "costo_usd": data.cost_usd,
                "existencia_inicial": initial_stock,
            },
        )
    product = repo.get(conn, product_id)
    assert product is not None
    return product


# ------------------------------------------------------------------ edición


def update_product(conn: sqlite3.Connection, user: User, product_id: int, data: ProductData) -> Product:
    """RF-13: edición (solo la dueña). Cambios de precio y costo quedan en bitácora con antes y después."""
    require_owner(user, "editar productos")
    data = clean_product_data(data)
    with transaction(conn):
        old = repo.get(conn, product_id)
        if old is None:
            raise LookupError("El producto no existe.")
        if not data.allows_fraction and old.stock != old.stock.to_integral_value():
            raise ValueError("La existencia tiene decimales: no se puede quitar la venta por fracción.")
        _check_category(conn, data)
        _check_barcode(conn, data, product_id)
        repo.update(conn, product_id, data, _search_text(conn, old.code, data))
        if data.price_usd != old.data.price_usd:
            audit(
                conn,
                user.id,
                "PRICE_CHANGE",
                "product",
                product_id,
                {"codigo": old.code, "antes": old.data.price_usd, "despues": data.price_usd},
            )
        if data.cost_usd != old.data.cost_usd:
            audit(
                conn,
                user.id,
                "COST_CHANGE",
                "product",
                product_id,
                {"codigo": old.code, "antes": old.data.cost_usd, "despues": data.cost_usd},
            )
        other = {
            k: {"antes": getattr(old.data, k), "despues": getattr(data, k)}
            for k in (f.name for f in fields(ProductData))
            if k not in ("price_usd", "cost_usd") and getattr(old.data, k) != getattr(data, k)
        }
        if other:
            audit(conn, user.id, "PRODUCT_UPDATED", "product", product_id, {"codigo": old.code, **_jsonable(other)})
    product = repo.get(conn, product_id)
    assert product is not None
    return product


def _jsonable(d: dict) -> dict:
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _jsonable(v)
        elif hasattr(v, "value"):
            out[k] = v.value
        else:
            out[k] = v
    return out


def set_active(conn: sqlite3.Connection, user: User, product_id: int, active: bool) -> None:
    """RF-15: desactivar (nunca borrar). Los inactivos no salen en la venta."""
    require_owner(user, "activar o desactivar productos")
    with transaction(conn):
        old = repo.get(conn, product_id)
        if old is None:
            raise LookupError("El producto no existe.")
        if old.active == active:
            return
        repo.set_active(conn, product_id, active)
        audit(
            conn,
            user.id,
            "PRODUCT_ACTIVATED" if active else "PRODUCT_DEACTIVATED",
            "product",
            product_id,
            {"codigo": old.code},
        )


def regenerate_search_text(conn: sqlite3.Connection, product_ids: list[int]) -> None:
    """Rehace search_text (p. ej. al renombrar una categoría). Debe llamarse dentro de una transacción."""
    for pid in product_ids:
        p = repo.get(conn, pid)
        if p is not None:
            repo.set_search_text(conn, pid, _search_text(conn, p.code, p.data))


# ------------------------------------------------------------------ consulta


def get_product(conn: sqlite3.Connection, user: User, product_id: int) -> Product:
    """Ficha completa para editar, con costo: solo la dueña."""
    require_owner(user, "ver el costo de los productos")
    p = repo.get(conn, product_id)
    if p is None:
        raise LookupError("El producto no existe.")
    return p


def get_view(conn: sqlite3.Connection, user: User, product_id: int) -> ProductView:
    """Ficha de solo lectura; para el vendedor, sin costo."""
    p = repo.get(conn, product_id)
    if p is None:
        raise LookupError("El producto no existe.")
    return _views(conn, user, [p])[0]


def _views(
    conn: sqlite3.Connection, user: User, products: list[Product], today: date | None = None
) -> list[ProductView]:
    rate = rate_service.current_rate(conn, today)
    multiple = settings_service.load(conn).rounding_multiple
    return [_to_view(p, user, rate.rate if rate else None, multiple) for p in products]


def search(
    conn: sqlite3.Connection,
    user: User,
    query: str,
    include_inactive: bool = False,
    limit: int = SEARCH_LIMIT,
    today: date | None = None,
) -> list[ProductView]:
    """RF-12: varias palabras en cualquier orden, sin mayúsculas ni acentos; código de barras exacto primero."""
    if include_inactive and not user.is_owner:
        include_inactive = False
    words = search_words(query)
    exact = query.strip() or None
    products = repo.search(conn, words, exact, include_inactive, limit)
    if exact:
        # Código de barras o código propio exacto: siempre primero, aunque sus "palabras" no coincidan
        hit = repo.find_exact(conn, exact, include_inactive)
        if hit is not None:
            products = [hit, *[p for p in products if p.id != hit.id]][:limit]
    return _views(conn, user, products, today)


def find_by_scan(conn: sqlite3.Connection, user: User, text: str) -> ProductView | None:
    """Lo que entrega el lector de código de barras: coincidencia exacta de código de barras o código propio."""
    hit = repo.find_exact(conn, text.strip())
    return _views(conn, user, [hit])[0] if hit else None


def count_low_stock(conn: sqlite3.Connection) -> int:
    return repo.count_low_stock(conn)
