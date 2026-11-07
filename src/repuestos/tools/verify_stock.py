"""Verificación de existencias (RF-44): ``products.stock_e3`` contra la suma de ``inventory_movements``.

Uso: ``python -m repuestos.tools.verify_stock`` (usa la base de ``REPUESTOS_DATA_DIR`` o la de ProgramData).
Sale con código 0 si todo cuadra y 1 si hay diferencias. Al arrancar el programa se corre en silencio.
"""

from __future__ import annotations

import sqlite3
import sys

from repuestos.db.connection import transaction
from repuestos.db.repositories.inventory import StockMismatch, stock_mismatches
from repuestos.services.audit_service import audit


def verify(conn: sqlite3.Connection) -> list[StockMismatch]:
    return stock_mismatches(conn)


def verify_and_log(conn: sqlite3.Connection) -> list[StockMismatch]:
    """Al arrancar: si hay diferencias, deja constancia en la bitácora."""
    mismatches = stock_mismatches(conn)
    if mismatches:
        with transaction(conn):
            audit(
                conn,
                None,
                "STOCK_MISMATCH",
                "product",
                None,
                {
                    "productos": [
                        {"id": m.product_id, "codigo": m.code, "existencia": m.stock, "movimientos": m.ledger}
                        for m in mismatches[:50]
                    ],
                    "total": len(mismatches),
                },
            )
    return mismatches


def main() -> int:
    from repuestos.config import get_paths
    from repuestos.db.connection import connect

    paths = get_paths()
    if not paths.db_path.exists():
        print(f"No existe la base de datos {paths.db_path}")
        return 2
    conn = connect(paths.db_path)
    try:
        mismatches = verify(conn)
    finally:
        conn.close()
    if not mismatches:
        print("Existencias correctas: todas cuadran con sus movimientos.")
        return 0
    print(f"{len(mismatches)} producto(s) con diferencias:")
    for m in mismatches:
        print(
            f"  {m.code} {m.name}: existencia {m.stock}, suma de movimientos {m.ledger},"
            f" último movimiento {m.last_stock_after}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
