"""Producto (RF-10) y su validación."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from repuestos.domain.money import hu


class Unit(StrEnum):
    UNIDAD = "UNIDAD"
    PAR = "PAR"
    JUEGO = "JUEGO"
    DOCENA = "DOCENA"
    METRO = "METRO"
    LITRO = "LITRO"


UNIT_LABELS = {
    Unit.UNIDAD: "Unidad",
    Unit.PAR: "Par",
    Unit.JUEGO: "Juego",
    Unit.DOCENA: "Docena",
    Unit.METRO: "Metro",
    Unit.LITRO: "Litro",
}

#: Abreviatura para mostrar junto a la cantidad ("9 jgo", "2,5 m").
UNIT_SHORT = {
    Unit.UNIDAD: "u",
    Unit.PAR: "par",
    Unit.JUEGO: "jgo",
    Unit.DOCENA: "doc",
    Unit.METRO: "m",
    Unit.LITRO: "L",
}


@dataclass(frozen=True, slots=True)
class ProductData:
    """Datos editables de la ficha (sin código, existencia ni estado)."""

    name: str
    brand: str = ""
    compatible_models: str = ""
    category_id: int | None = None
    location: str = ""
    unit: Unit = Unit.UNIDAD
    allows_fraction: bool = False
    barcode: str | None = None
    price_usd: Decimal = Decimal("0")
    cost_usd: Decimal = Decimal("0")
    min_stock: Decimal = Decimal("10")


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    code: str
    data: ProductData
    category_name: str
    stock: Decimal
    active: bool

    @property
    def name(self) -> str:
        return self.data.name

    @property
    def is_low(self) -> bool:
        """RN-10: para pedir si está activo, mínimo > 0 y existencia <= mínimo."""
        return self.active and self.data.min_stock > 0 and self.stock <= self.data.min_stock


def _max_decimals(value: Decimal, digits: int, label: str) -> None:
    if value != hu(value, digits):
        raise ValueError(f"{label} admite como máximo {digits} decimales.")


def clean_product_data(data: ProductData) -> ProductData:
    """Valida y normaliza la ficha. Lanza ValueError con un mensaje para la usuaria."""
    name = " ".join(data.name.split())
    if not name:
        raise ValueError("Escriba el nombre del producto.")
    barcode = (data.barcode or "").strip() or None
    if data.price_usd < 0:
        raise ValueError("El precio no puede ser negativo.")
    if data.cost_usd < 0:
        raise ValueError("El costo no puede ser negativo.")
    if data.min_stock < 0:
        raise ValueError("El mínimo no puede ser negativo.")
    _max_decimals(data.price_usd, 4, "El precio en USD")
    _max_decimals(data.cost_usd, 4, "El costo en USD")
    _max_decimals(data.min_stock, 3, "El mínimo")
    if not data.allows_fraction and data.min_stock != data.min_stock.to_integral_value():
        raise ValueError("El mínimo debe ser un número entero si el producto no se vende por fracción.")
    return ProductData(
        name=name,
        brand=data.brand.strip(),
        compatible_models=data.compatible_models.strip(),
        category_id=data.category_id,
        location=data.location.strip(),
        unit=Unit(data.unit),
        allows_fraction=data.allows_fraction,
        barcode=barcode,
        price_usd=hu(data.price_usd, 4),
        cost_usd=hu(data.cost_usd, 4),
        min_stock=hu(data.min_stock, 3),
    )
