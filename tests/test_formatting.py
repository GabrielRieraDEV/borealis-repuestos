from datetime import date
from decimal import Decimal as D

import pytest

from repuestos.formatting import format_date, format_rate, format_usd, format_ves, parse_decimal


def test_format_amounts() -> None:
    assert format_ves(D("1234.56")) == "Bs 1.234,56"
    assert format_ves(D("10872.5")) == "Bs 10.872,50"
    assert format_ves(D("-113.61")) == "Bs -113,61"
    assert format_usd(D("12.5")) == "USD 12,50"
    assert format_usd(D("1234567.891")) == "USD 1.234.567,89"
    assert format_rate(D("231.046800")) == "231,0468"


def test_format_date() -> None:
    assert format_date(date(2026, 11, 7)) == "07/11/2026"
    assert format_date("2026-11-07 09:30:00") == "07/11/2026"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5,00", D("5.00")),
        ("1.234,56", D("1234.56")),
        ("1.234", D("1234")),
        ("12.5", D("12.5")),
        ("231,0468", D("231.0468")),
        (" 1234 ", D("1234")),
        ("Bs 2.890,00", D("2890.00")),
    ],
)
def test_parse_decimal(text: str, expected: D) -> None:
    assert parse_decimal(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "1,2,3", "nan", "inf"])
def test_parse_decimal_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_decimal(text)
