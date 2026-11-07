"""Dinero, cantidades y redondeo (docs/02, notación HU y TECHO; docs/03, escalas de enteros).

Reglas:
- Nunca ``float``. Todo es ``Decimal``.
- El redondeo siempre es explícito: ``hu`` (ROUND_HALF_UP) o ``techo`` (múltiplo hacia arriba).
- ``to_db`` falla si el valor trae más decimales que la escala: hay que redondear antes, en el dominio.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Context, Decimal
from typing import Final, Literal

Scale = Literal["e2", "e3", "e4", "e6", "bp"]

#: Decimales de cada escala (sufijo de la columna en SQLite).
SCALE_DIGITS: Final[dict[str, int]] = {
    "e2": 2,  # montos y totales (USD o Bs)
    "e3": 3,  # cantidades y existencias
    "e4": 4,  # precio o costo unitario USD
    "e6": 6,  # tasa Bs por USD
    "bp": 2,  # porcentajes (16 % -> 1600)
}

# Contexto amplio para divisiones intermedias: el redondeo final lo decide hu/techo.
_WIDE = Context(prec=50)

ZERO: Final = Decimal(0)


def _check_decimal(value: object, what: str = "valor") -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise TypeError(f"{what} debe ser Decimal, no {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{what} no es un número finito: {value}")
    return value


def to_db(value: Decimal, scale: Scale) -> int:
    """Convierte un Decimal al entero escalado de la columna. Falla si sobran decimales."""
    _check_decimal(value)
    digits = SCALE_DIGITS[scale]
    scaled = value.scaleb(digits, _WIDE)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{value} tiene más de {digits} decimales para la escala _{scale}; redondee antes")
    return int(scaled)


def from_db(value: int, scale: Scale) -> Decimal:
    """Convierte el entero escalado de la columna a Decimal con los decimales de la escala."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"se esperaba int, no {type(value).__name__}")
    digits = SCALE_DIGITS[scale]
    return Decimal(value).scaleb(-digits)


def hu(x: Decimal, n: int) -> Decimal:
    """HU(x, n): redondea ``x`` a ``n`` decimales con ROUND_HALF_UP (docs/02)."""
    _check_decimal(x)
    return x.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP, context=_WIDE)


def techo(x: Decimal, m: Decimal) -> Decimal:
    """TECHO(x, m): el menor múltiplo de ``m`` que sea >= ``x`` (docs/02, RN-03)."""
    _check_decimal(x)
    _check_decimal(m, "múltiplo")
    if m <= 0:
        raise ValueError("el múltiplo de redondeo debe ser mayor que cero")
    steps = _WIDE.divide(x, m).to_integral_value(rounding=ROUND_CEILING)
    return _WIDE.multiply(steps, m)


def div(a: Decimal, b: Decimal) -> Decimal:
    """División con precisión amplia, sin redondeo de negocio (aplicar hu/techo después)."""
    _check_decimal(a)
    _check_decimal(b)
    return _WIDE.divide(a, b)


def mul(a: Decimal, b: Decimal) -> Decimal:
    """Multiplicación exacta con precisión amplia."""
    _check_decimal(a)
    _check_decimal(b)
    return _WIDE.multiply(a, b)


def percent_factor(rate_bp: int) -> Decimal:
    """1 + porcentaje. 1600 bp -> Decimal('1.16')."""
    return Decimal(1) + from_db(rate_bp, "bp") / Decimal(100)
