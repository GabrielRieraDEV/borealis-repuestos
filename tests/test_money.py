from decimal import Decimal as D

import pytest

from repuestos.domain.money import from_db, hu, techo, to_db


@pytest.mark.parametrize(
    ("value", "scale", "expected"),
    [
        (D("12.5"), "e4", 125000),
        (D("1234.56"), "e2", 123456),
        (D("2.5"), "e3", 2500),
        (D("231.046800"), "e6", 231046800),
        (D("231.0468"), "e6", 231046800),
        (D("16"), "bp", 1600),
        (D("10.6000"), "e4", 106000),
        (D("-3"), "e3", -3000),
        (D("0"), "e2", 0),
    ],
)
def test_to_db(value: D, scale: str, expected: int) -> None:
    assert to_db(value, scale) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "scale", "expected"),
    [(289000, "e2", D("2890.00")), (106000, "e4", D("10.6000")), (2500, "e3", D("2.500")), (1600, "bp", D("16"))],
)
def test_from_db(value: int, scale: str, expected: D) -> None:
    assert from_db(value, scale) == expected  # type: ignore[arg-type]


def test_round_trip_keeps_scale_digits() -> None:
    assert str(from_db(to_db(D("2890"), "e2"), "e2")) == "2890.00"


def test_to_db_rejects_extra_decimals() -> None:
    with pytest.raises(ValueError):
        to_db(D("2888.085"), "e2")
    with pytest.raises(ValueError):
        to_db(D("1.0001"), "e3")


def test_to_db_rejects_float_and_bool() -> None:
    with pytest.raises(TypeError):
        to_db(12.5, "e4")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        to_db(True, "e2")  # type: ignore[arg-type]


def test_from_db_rejects_non_int() -> None:
    with pytest.raises(TypeError):
        from_db(1.5, "e2")  # type: ignore[arg-type]


def test_hu_is_half_up_not_half_even() -> None:
    assert hu(D("2.5"), 0) == D("3")  # HALF_EVEN daría 2
    assert hu(D("0.125"), 2) == D("0.13")  # HALF_EVEN daría 0.12
    assert hu(D("-0.125"), 2) == D("-0.13")
    assert hu(D("12.50835"), 4) == D("12.5084")


def test_techo() -> None:
    assert techo(D("2888.085"), D("5")) == D("2890")
    assert techo(D("2890"), D("5")) == D("2890")
    assert techo(D("184.83744"), D("0.01")) == D("184.84")
    assert techo(D("0"), D("5")) == D("0")


def test_techo_rejects_zero_multiple() -> None:
    with pytest.raises(ValueError):
        techo(D("1"), D("0"))
