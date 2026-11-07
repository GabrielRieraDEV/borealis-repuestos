import json
import sqlite3
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from repuestos.db.repositories.exchange_rates import RateSource
from repuestos.services import rate_service
from repuestos.services.bcv import BcvError, parse_bcv_html
from tests.helpers import as_seller

FIXTURE = Path(__file__).parent / "fixtures" / "bcv.html"
FRI = date(2026, 11, 6)
SAT = date(2026, 11, 7)
MON = date(2026, 11, 9)


# ------------------------------------------------------------------ parser BCV


def test_parse_bcv_fixture() -> None:
    """HTML real del 07/11/2026: USD 897,53830000 con fecha valor lunes 09/11/2026 (publicada por adelantado)."""
    r = parse_bcv_html(FIXTURE.read_text(encoding="utf-8"))
    assert r.rate == D("897.538300")
    assert r.valid_date == MON


def test_parse_rounds_to_six_decimals_half_up() -> None:
    html = (
        '<div id="dolar"><div><strong> 231,04680050 </strong></div></div>'
        '<span property="dc:date" content="2026-11-06T00:00:00-04:00">x</span>'
    )
    assert parse_bcv_html(html).rate == D("231.046801")


def test_parse_ignores_other_currencies_before_dolar() -> None:
    html = (
        '<div id="euro"><strong>999,00</strong></div>'
        '<span property="dc:date" content="2020-01-01T00:00:00">viejo</span>'
        '<div id="dolar"><strong>231,0468</strong></div>'
        '<span property="dc:date" content="2026-11-06T00:00:00-04:00">x</span>'
    )
    r = parse_bcv_html(html)
    assert (r.rate, r.valid_date) == (D("231.046800"), FRI)


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>mantenimiento</body></html>",
        '<div id="dolar"></div><span property="dc:date" content="2026-11-06">x</span>',
        '<div id="dolar"><strong>231,04</strong></div>',
        '<div id="dolar"><strong>abc</strong></div><span property="dc:date" content="2026-11-06">x</span>',
        '<div id="dolar"><strong>231,04</strong></div><span property="dc:date" content="ayer">x</span>',
    ],
)
def test_parse_errors(html: str) -> None:
    with pytest.raises(BcvError):
        parse_bcv_html(html)


# ------------------------------------------------------------------ RN-01 tasa vigente


def test_no_rate(conn: sqlite3.Connection) -> None:
    assert rate_service.current_rate(conn, SAT) is None
    with pytest.raises(LookupError, match="Tasa BCV"):
        rate_service.require_rate(conn, SAT)


def test_future_value_date_is_not_current_yet(conn: sqlite3.Connection) -> None:
    """RN-01: el viernes el BCV publica la del lunes; el sábado sigue vigente la del viernes."""
    rate_service.save_bcv_rate(conn, D("230.0000"), FRI)
    rate_service.save_bcv_rate(conn, D("231.0468"), MON)
    assert rate_service.current_rate(conn, SAT).rate == D("230.0000")
    assert rate_service.current_rate(conn, SAT).valid_date == FRI
    assert rate_service.current_rate(conn, MON).rate == D("231.0468")


def test_only_future_rate_means_no_rate(conn: sqlite3.Connection) -> None:
    rate_service.save_bcv_rate(conn, D("231.0468"), MON)
    assert rate_service.current_rate(conn, SAT) is None


def test_stale_after_three_days(conn: sqlite3.Connection) -> None:
    rate_service.save_bcv_rate(conn, D("230"), date(2026, 11, 3))
    assert not rate_service.current_rate(conn, date(2026, 11, 6)).stale  # 3 días
    assert rate_service.current_rate(conn, date(2026, 11, 7)).stale  # 4 días


def test_manual_rate(conn: sqlite3.Connection, owner) -> None:
    rate_service.set_manual_rate(conn, owner, D("240.00"), today=SAT)
    r = rate_service.current_rate(conn, SAT)
    assert (r.rate, r.valid_date, r.source) == (D("240.00"), SAT, RateSource.MANUAL)
    row = conn.execute("SELECT user_id FROM exchange_rates").fetchone()
    assert row[0] == owner.id


def test_manual_rate_replaces_and_audits_previous(conn: sqlite3.Connection, owner) -> None:
    rate_service.save_bcv_rate(conn, D("231.0468"), SAT)
    rate_service.set_manual_rate(conn, owner, D("240.00"), today=SAT)
    assert conn.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 1
    details = json.loads(conn.execute("SELECT details_json FROM audit_log WHERE action = 'RATE_MANUAL'").fetchone()[0])
    assert details == {
        "fecha_valor": "2026-11-07",
        "tasa": "240.00",
        "tasa_anterior": "231.046800",
        "origen_anterior": "BCV_AUTO",
    }


def test_seller_cannot_set_manual_rate(conn: sqlite3.Connection, owner) -> None:
    with pytest.raises(PermissionError):
        rate_service.set_manual_rate(conn, as_seller(owner), D("240"), today=SAT)


def test_manual_rate_validation(conn: sqlite3.Connection, owner) -> None:
    with pytest.raises(ValueError):
        rate_service.set_manual_rate(conn, owner, D("0"), today=SAT)
    with pytest.raises(ValueError):
        rate_service.set_manual_rate(conn, owner, D("231.0468001"), today=SAT)


def test_bcv_does_not_override_manual(conn: sqlite3.Connection, owner) -> None:
    rate_service.set_manual_rate(conn, owner, D("240.00"), today=SAT)
    assert rate_service.save_bcv_rate(conn, D("231.0468"), SAT) is False
    assert rate_service.current_rate(conn, SAT).rate == D("240.00")


def test_bcv_correction_updates_auto_rate(conn: sqlite3.Connection) -> None:
    assert rate_service.save_bcv_rate(conn, D("231.0468"), MON) is True
    assert rate_service.save_bcv_rate(conn, D("231.0468"), MON) is False
    assert rate_service.save_bcv_rate(conn, D("231.5000"), MON) is True
    assert rate_service.current_rate(conn, MON).rate == D("231.5000")
