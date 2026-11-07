from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal

from repuestos.domain.products import ProductData, Unit
from repuestos.domain.users import Role, User
from repuestos.services import user_service


def make_seller(conn: sqlite3.Connection, owner: User) -> User:
    return user_service.create_seller(conn, owner, "pedro", "Pedro Pérez", "vende123")


def as_seller(owner: User) -> User:
    return replace(owner, role=Role.SELLER)


def category_id(conn: sqlite3.Connection, name: str) -> int:
    return conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()[0]


def pastillas(conn: sqlite3.Connection, **overrides: object) -> ProductData:
    """Producto de ejemplo del PRD (RF-12)."""
    base = ProductData(
        name="Pastillas de freno delanteras — Bera 150",
        brand="Genérica",
        compatible_models="Bera 150, Empire Owen 150",
        category_id=category_id(conn, "Frenos"),
        location="A-3",
        unit=Unit.JUEGO,
        price_usd=Decimal("12.50"),
        cost_usd=Decimal("7.00"),
        min_stock=Decimal("10"),
    )
    return replace(base, **overrides)  # type: ignore[arg-type]
