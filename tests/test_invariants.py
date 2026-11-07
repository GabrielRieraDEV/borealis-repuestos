"""Invariantes de docs/03. En esta fase: la 1 (existencias = movimientos) y verify_stock (RF-44)."""

import sqlite3
from decimal import Decimal as D

from repuestos.db.connection import transaction
from repuestos.domain.products import ProductData, Unit
from repuestos.services import product_service
from repuestos.tools import verify_stock
from tests.helpers import pastillas


def assert_stock_invariant(conn: sqlite3.Connection) -> None:
    assert verify_stock.verify(conn) == []


def test_invariant_1_after_product_operations(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("10"))
    product_service.create_product(
        conn, owner, ProductData(name="Cable", unit=Unit.METRO, allows_fraction=True), initial_stock=D("2.5")
    )
    product_service.create_product(conn, owner, ProductData(name="Sin existencia"))
    product_service.update_product(conn, owner, p.id, pastillas(conn, price_usd=D("13")))
    product_service.set_active(conn, owner, p.id, False)
    assert_stock_invariant(conn)


def test_verify_stock_detects_and_logs_difference(conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("10"))
    with transaction(conn):  # simula el error del sistema anterior: existencia cambiada sin movimiento
        conn.execute("UPDATE products SET stock_e3 = 7000 WHERE id = ?", (p.id,))
    (m,) = verify_stock.verify_and_log(conn)
    assert (m.code, m.stock, m.ledger, m.last_stock_after) == ("R-00001", D("7"), D("10"), D("10"))
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'STOCK_MISMATCH'").fetchone()[0] == 1


def test_verify_stock_silent_when_ok(conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn), initial_stock=D("10"))
    assert verify_stock.verify_and_log(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'STOCK_MISMATCH'").fetchone()[0] == 0
