import json
import sqlite3
from dataclasses import replace
from decimal import Decimal as D

import pytest

from repuestos.services import auth_service, category_service, settings_service, user_service
from tests.conftest import OWNER_PASSWORD
from tests.helpers import as_seller, make_seller

# ------------------------------------------------------------------ usuarios (RF-03)


def test_create_seller_and_login(conn: sqlite3.Connection, owner) -> None:
    seller = make_seller(conn, owner)
    assert not seller.is_owner
    assert auth_service.login(conn, "pedro", "vende123").id == seller.id


def test_seller_cannot_manage_users(conn: sqlite3.Connection, owner) -> None:
    seller = make_seller(conn, owner)
    with pytest.raises(PermissionError):
        user_service.create_seller(conn, seller, "otro", "Otro", "123456")
    with pytest.raises(PermissionError):
        user_service.list_users(conn, seller)


def test_duplicate_username(conn: sqlite3.Connection, owner) -> None:
    make_seller(conn, owner)
    with pytest.raises(ValueError, match="Ya existe"):
        user_service.create_seller(conn, owner, "PEDRO", "Otro", "123456")


def test_deactivate_seller_blocks_login(conn: sqlite3.Connection, owner) -> None:
    seller = make_seller(conn, owner)
    user_service.set_active(conn, owner, seller.id, False)
    with pytest.raises(auth_service.AuthError):
        auth_service.login(conn, "pedro", "vende123")
    with pytest.raises(ValueError):
        user_service.set_active(conn, owner, owner.id, False)


def test_reset_password_unlocks(conn: sqlite3.Connection, owner) -> None:
    seller = make_seller(conn, owner)
    for _ in range(5):
        with pytest.raises(auth_service.AuthError):
            auth_service.login(conn, "pedro", "mala")
    user_service.reset_password(conn, owner, seller.id, "nueva123")
    assert auth_service.login(conn, "pedro", "nueva123").id == seller.id


def test_authorize_owner(conn: sqlite3.Connection, owner) -> None:
    seller = make_seller(conn, owner)
    assert user_service.authorize_owner(conn, OWNER_PASSWORD, seller, "anular venta") == owner.id
    assert user_service.authorize_owner(conn, "vende123", seller, "anular venta") is None
    row = conn.execute("SELECT user_id, details_json FROM audit_log WHERE action = 'AUTHORIZATION_FAILED'").fetchone()
    assert row[0] == seller.id
    assert json.loads(row[1]) == {"accion": "anular venta"}


# ------------------------------------------------------------------ configuración (RF-06)


def test_settings_load_defaults(conn: sqlite3.Connection, owner) -> None:
    s = settings_service.load(conn)
    assert s.rounding_multiple == D("5.00")
    assert s.default_min_stock == D("10")
    assert s.default_credit_days == 15
    assert not s.allow_negative_stock
    assert not s.payment_usdt_enabled
    assert s.igtf_percent == 0


def test_settings_save_and_audit(conn: sqlite3.Connection, owner) -> None:
    s = settings_service.load(conn)
    new = replace(s, rounding_multiple=D("10.00"), allow_negative_stock=True, business_phone="0414-1234567")
    settings_service.save(conn, owner, new)
    assert settings_service.load(conn) == new
    details = json.loads(
        conn.execute("SELECT details_json FROM audit_log WHERE action = 'SETTINGS_CHANGED'").fetchone()[0]
    )
    assert set(details) == {"rounding_multiple", "allow_negative_stock", "business_phone"}
    assert details["rounding_multiple"] == {"antes": "5.00", "despues": "10.00"}


def test_settings_no_change_no_audit(conn: sqlite3.Connection, owner) -> None:
    settings_service.save(conn, owner, settings_service.load(conn))
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'SETTINGS_CHANGED'").fetchone()[0] == 0


def test_settings_seller_forbidden(conn: sqlite3.Connection, owner) -> None:
    with pytest.raises(PermissionError):
        settings_service.save(conn, as_seller(owner), settings_service.load(conn))


@pytest.mark.parametrize(
    "change",
    [{"rounding_multiple": D("0")}, {"default_credit_days": 0}, {"business_name": ""}, {"igtf_percent": D("-1")}],
)
def test_settings_validation(conn: sqlite3.Connection, owner, change: dict) -> None:
    with pytest.raises(ValueError):
        settings_service.save(conn, owner, replace(settings_service.load(conn), **change))


# ------------------------------------------------------------------ categorías (RF-14)


def test_categories_seed_and_crud(conn: sqlite3.Connection, owner) -> None:
    names = [c.name for c in category_service.list_categories(conn)]
    assert len(names) == 10 and "Frenos" in names
    cid = category_service.create_category(conn, owner, "Lubricantes")
    with pytest.raises(ValueError, match="Ya existe"):
        category_service.create_category(conn, owner, "lubricantes")
    category_service.set_active(conn, owner, cid, False)
    assert "Lubricantes" not in [c.name for c in category_service.list_categories(conn)]
    assert category_service.create_category(conn, owner, "Lubricantes") == cid  # se reactiva
    with pytest.raises(PermissionError):
        category_service.create_category(conn, as_seller(owner), "X")
