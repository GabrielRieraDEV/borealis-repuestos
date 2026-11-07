"""Formato de montos, tasas y fechas para la pantalla (RNF-08). Sin Qt, para poder probarlo.

``Bs 1.234,56`` · ``USD 12,50`` · ``dd/mm/aaaa``: punto de miles y coma decimal.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from repuestos.domain.money import hu


def format_number(value: Decimal, decimals: int = 2) -> str:
    rounded = hu(value, decimals)
    text = f"{abs(rounded):,.{decimals}f}"  # formato inglés: 1,234.56
    text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"-{text}" if rounded < 0 else text


def format_ves(value: Decimal) -> str:
    return f"Bs {format_number(value, 2)}"


def format_usd(value: Decimal, decimals: int = 2) -> str:
    return f"USD {format_number(value, decimals)}"


def format_rate(value: Decimal) -> str:
    """Tasa con 4 decimales, como la publica el BCV en pantalla (231,0468)."""
    return format_number(value, 4)


def format_date(value: date | datetime | str) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d/%m/%Y")


_THOUSANDS_DOTS = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_decimal(text: str) -> Decimal:
    """Lee un número escrito por la usuaria: '1.234,56', '5,00', '12.5', '1234'.

    Lanza ValueError con un mensaje claro si no es un número.
    """
    raw = text.strip().replace(" ", "")
    if raw.upper().startswith(("BS", "USD")):
        raw = re.sub(r"^(BS|USD)", "", raw, flags=re.IGNORECASE)
    if not raw:
        raise ValueError("Escriba un número.")
    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    elif _THOUSANDS_DOTS.match(raw):
        normalized = raw.replace(".", "")
    else:
        normalized = raw
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        raise ValueError(f"'{text}' no es un número válido.") from None
    if not value.is_finite():
        raise ValueError(f"'{text}' no es un número válido.")
    return value
