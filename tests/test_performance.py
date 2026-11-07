"""RNF-05 · con 5.000 productos y 50.000 ventas: arranque < 5 s, búsqueda < 300 ms, guardar una venta < 1 s."""

from __future__ import annotations

import random
import time
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from repuestos.db.connection import connect, transaction
from repuestos.db.migrate import apply_migrations
from repuestos.domain.sale import PaymentInput, PaymentMethod
from repuestos.services import cash_service, product_service, rate_service, report_service, sale_service, setup_service
from repuestos.services.sale_service import CartItem
from repuestos.tools.verify_stock import verify_and_log

N_PRODUCTS = 5_000
N_SALES = 50_000


def _populate(path: Path):
    conn = connect(path)
    apply_migrations(conn)
    owner = setup_service.complete_setup(
        conn, setup_service.SetupData("duena", "Dueña", "clave123", "Romero", "V-1", "", "", D("5"))
    )
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    session = cash_service.open_session(conn, owner, D("0"), D("0"))
    rnd = random.Random(5)
    parts = ["Pastillas de freno", "Bujía", "Cadena", "Piñón", "Corona", "Filtro de aceite", "Guaya", "Bombillo"]
    models = ["Bera 150", "Owen 150", "Horse 150", "Speed 200", "Jaguar 150", "GN 125"]
    start = date.today() - timedelta(days=365)
    with transaction(conn):
        conn.executemany(
            "INSERT INTO products (code, name, compatible_models, price_usd_e4, cost_usd_e4, stock_e3, search_text)"
            " VALUES (?, ?, ?, ?, ?, 0, ?)",
            [
                (
                    f"R-{i:05d}",
                    f"{parts[i % 8]} {i}",
                    models[i % 6],
                    rnd.randint(1, 50) * 10000,
                    5000,
                    f"{parts[i % 8].lower()} {i} {models[i % 6].lower()} r {i:05d}",
                )
                for i in range(1, N_PRODUCTS + 1)
            ],
        )
        conn.execute("UPDATE doc_sequences SET next_number = ? WHERE doc_type = 'R'", (N_PRODUCTS + 1,))
        conn.executemany(
            "INSERT INTO inventory_movements (product_id, type, qty_e3, stock_after_e3, unit_cost_usd_e4, user_id)"
            " VALUES (?, 'INITIAL', 1000000000, 1000000000, 5000, 1)",
            [(i,) for i in range(1, N_PRODUCTS + 1)],
        )
        sales, items, payments, moves = [], [], [], []
        for n in range(1, N_SALES + 1):
            day = start + timedelta(days=n * 365 // N_SALES)
            ts = f"{day.isoformat()} 10:00:00"
            sales.append((n, session.id, ts))
            for pid in (rnd.randint(1, N_PRODUCTS), rnd.randint(1, N_PRODUCTS)):
                items.append((n, pid))
                moves.append((pid, n, ts))
            payments.append((session.id, n, ts))
        conn.executemany(
            "INSERT INTO sales (id, number, session_id, customer_id, user_id, rate_e6, total_ves_e2, base_ves_e2,"
            " vat_ves_e2, total_usd_e2, base_usd_e2, created_at) VALUES (?1, ?1, ?2, 1, 1, 231046800, 116000,"
            " 100000, 16000, 500, 431, ?3)",
            sales,
        )
        conn.executemany(
            "INSERT INTO sale_items (sale_id, product_id, description, qty_e3, unit_price_usd_e4, unit_price_ves_e2,"
            " line_total_ves_e2, line_total_usd_e2, unit_cost_usd_e4, line_cost_usd_e2, vat_rate_bp)"
            " VALUES (?, ?, 'x', 1000, 25000, 58000, 58000, 250, 5000, 50, 1600)",
            items,
        )
        conn.executemany(
            "INSERT INTO payments (session_id, sale_id, method, currency, amount_e2, amount_ves_e2, created_at)"
            " VALUES (?, ?, 'POS', 'VES', 116000, 116000, ?)",
            payments,
        )
        conn.executemany(
            "INSERT INTO inventory_movements (product_id, type, qty_e3, stock_after_e3, unit_cost_usd_e4, sale_id,"
            " user_id, created_at) VALUES (?, 'SALE', -1000, 0, 5000, ?, 1, ?)",
            moves,
        )
        conn.execute("UPDATE doc_sequences SET next_number = ? WHERE doc_type = 'NE'", (N_SALES + 1,))
        # existencia y stock_after coherentes con los movimientos (invariante 1)
        conn.execute(
            "UPDATE products SET stock_e3 ="
            " (SELECT SUM(qty_e3) FROM inventory_movements m WHERE m.product_id = products.id)"
        )
        conn.execute(
            "UPDATE inventory_movements SET stock_after_e3 = (SELECT SUM(m2.qty_e3) FROM inventory_movements m2"
            " WHERE m2.product_id = inventory_movements.product_id AND m2.id <= inventory_movements.id)"
            " WHERE type = 'SALE'"
        )
    return conn, owner


@pytest.mark.slow
def test_rnf05_rendimiento(tmp_path: Path) -> None:
    path = tmp_path / "grande.db"
    conn, owner = _populate(path)
    conn.close()
    assert conn is not None

    # arranque: lo que corre antes del login (sin contar la carga de Qt)
    t0 = time.perf_counter()
    conn = connect(path)
    apply_migrations(conn)
    report_service.ensure_monthly_snapshot(conn)
    assert verify_and_log(conn) == []
    startup = time.perf_counter() - t0

    worst_search = 0.0
    for q in ["pastilla bera 150", "bujia", "cadena horse", "R-04999", "filtro aceite gn 125", ""]:
        t0 = time.perf_counter()
        product_service.search(conn, owner, q)
        worst_search = max(worst_search, time.perf_counter() - t0)

    rate = rate_service.require_rate(conn).rate
    t0 = time.perf_counter()
    sale = sale_service.charge(
        conn,
        owner,
        [CartItem(10, D("1")), CartItem(4999, D("2"))],
        [PaymentInput(PaymentMethod.CASH_USD, D("200"))],
        rate,
    )
    charge = time.perf_counter() - t0
    assert sale.number == N_SALES + 1

    t0 = time.perf_counter()
    today = date.today()
    report_service.month_summary(conn, owner, today.year, today.month)
    report_service.daily_sales(conn, owner, today)
    reports = time.perf_counter() - t0
    conn.close()

    timings = (
        f"arranque {startup:.2f} s · búsqueda {worst_search * 1000:.0f} ms"
        f" · venta {charge * 1000:.0f} ms · reportes {reports:.2f} s"
    )
    print(timings)
    assert startup < 3.0, timings  # deja margen para cargar Qt dentro de los 5 s
    assert worst_search < 0.300, timings
    assert charge < 1.0, timings
    assert reports < 5.0, timings
