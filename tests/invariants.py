"""Invariantes de docs/03-modelo-de-datos.md, como funciones que devuelven la lista de violaciones."""

from __future__ import annotations

import sqlite3


def inv1_stock(conn: sqlite3.Connection) -> list[str]:
    from repuestos.tools.verify_stock import verify

    return [f"{m.code}: existencia {m.stock} vs movimientos {m.ledger}" for m in verify(conn)]


def inv2_sale_totals(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT s.id, s.total_ves_e2, s.total_usd_e2, s.base_ves_e2 + s.vat_ves_e2 AS bv,
               COALESCE(SUM(i.line_total_ves_e2), 0) AS lv, COALESCE(SUM(i.line_total_usd_e2), 0) AS lu
        FROM sales s LEFT JOIN sale_items i ON i.sale_id = s.id GROUP BY s.id
        """
    )
    return [
        f"venta {r['id']}"
        for r in rows
        if r["total_ves_e2"] != r["lv"] or r["total_usd_e2"] != r["lu"] or r["bv"] != r["total_ves_e2"]
    ]


def inv3_paid(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT s.id, s.total_ves_e2, s.credit_ves_e2,
               COALESCE((SELECT SUM(amount_ves_e2) FROM payments p WHERE p.sale_id = s.id AND p.voided = 0), 0) AS paid
        FROM sales s WHERE s.status = 'COMPLETED'
        """
    )
    return [f"venta {r['id']}" for r in rows if r["paid"] + r["credit_ves_e2"] != r["total_ves_e2"]]


def inv4_receivables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT r.id, r.amount_usd_e2, r.balance_usd_e2, r.status,
               COALESCE((SELECT SUM(a.amount_usd_e2) FROM credit_allocations a
                         JOIN credit_payments p ON p.id = a.credit_payment_id
                         WHERE a.receivable_id = r.id AND p.status = 'COMPLETED'), 0) AS paid
        FROM receivables r
        """
    )
    out = []
    for r in rows:
        if r["balance_usd_e2"] != r["amount_usd_e2"] - r["paid"]:
            out.append(f"deuda {r['id']}: saldo no cuadra con los abonos")
        if r["status"] != "VOIDED" and (r["status"] == "PAID") != (r["balance_usd_e2"] == 0):
            out.append(f"deuda {r['id']}: estado {r['status']} con saldo {r['balance_usd_e2']}")
    return out


def inv5_credit_payments(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT p.id, p.amount_usd_e2,
               COALESCE((SELECT SUM(amount_usd_e2) FROM credit_allocations a WHERE a.credit_payment_id = p.id), 0) AS al
        FROM credit_payments p
        """
    )
    return [f"abono {r['id']}" for r in rows if r["amount_usd_e2"] != r["al"]]


def inv6_cash(conn: sqlite3.Connection) -> list[str]:
    out = []
    if conn.execute("SELECT COUNT(*) FROM cash_sessions WHERE status = 'OPEN'").fetchone()[0] > 1:
        out.append("más de una caja abierta")
    for table in ("sales", "payments", "cash_movements", "credit_payments"):
        bad = conn.execute(
            f"SELECT COUNT(*) FROM {table} t JOIN cash_sessions s ON s.id = t.session_id"
            " WHERE t.created_at < s.opened_at OR (s.closed_at IS NOT NULL AND t.created_at > s.closed_at)"
        ).fetchone()[0]
        if bad:
            out.append(f"{table}: {bad} filas fuera de su sesión")
    return out


def inv7_numbers(conn: sqlite3.Connection) -> list[str]:
    out = []
    numbers = [r[0] for r in conn.execute("SELECT number FROM sales WHERE doc_type = 'NE' ORDER BY number")]
    if numbers != list(range(1, len(numbers) + 1)):
        out.append(f"notas con huecos: {numbers[:20]}")
    ab = [r[0] for r in conn.execute("SELECT number FROM credit_payments ORDER BY number")]
    if ab != list(range(1, len(ab) + 1)):
        out.append(f"abonos con huecos: {ab[:20]}")
    next_ne = conn.execute("SELECT next_number FROM doc_sequences WHERE doc_type = 'NE'").fetchone()[0]
    if next_ne != len(numbers) + 1:
        out.append(f"correlativo NE en {next_ne} con {len(numbers)} notas")
    return out


def inv8_voided(conn: sqlite3.Connection) -> list[str]:
    out = []
    for (sale_id,) in conn.execute("SELECT id FROM sales WHERE status = 'VOIDED'").fetchall():
        sales_mv = conn.execute(
            "SELECT product_id, -qty_e3 FROM inventory_movements WHERE sale_id = ? AND type = 'SALE' ORDER BY 1, 2",
            (sale_id,),
        ).fetchall()
        void_mv = conn.execute(
            "SELECT product_id, qty_e3 FROM inventory_movements WHERE sale_id = ? AND type = 'SALE_VOID' ORDER BY 1, 2",
            (sale_id,),
        ).fetchall()
        if [tuple(r) for r in sales_mv] != [tuple(r) for r in void_mv]:
            out.append(f"venta {sale_id}: movimientos de anulación no cuadran")
        if conn.execute("SELECT COUNT(*) FROM payments WHERE sale_id = ? AND voided = 0", (sale_id,)).fetchone()[0]:
            out.append(f"venta {sale_id}: pagos sin anular")
    return out


def all_violations(conn: sqlite3.Connection) -> list[str]:
    return [
        *inv1_stock(conn),
        *inv2_sale_totals(conn),
        *inv3_paid(conn),
        *inv4_receivables(conn),
        *inv5_credit_payments(conn),
        *inv6_cash(conn),
        *inv7_numbers(conn),
        *inv8_voided(conn),
    ]
