"""RNF-03 · prueba de corte de luz (plan Fase 3, criterio 10 del PRD).

Un subproceso cobra ventas en bucle y se mata de golpe a los N ms (TerminateProcess en Windows). Al reabrir:
integrity_check = ok, verify_stock sin diferencias y todas las invariantes (3 en todas las ventas). 20 veces.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from decimal import Decimal as D
from pathlib import Path

import pytest

from repuestos.db.connection import connect
from repuestos.db.migrate import apply_migrations
from repuestos.domain.products import ProductData
from repuestos.services import cash_service, product_service, rate_service, setup_service
from tests.invariants import all_violations

WORKER = Path(__file__).with_name("powercut_worker.py")
ROOT = Path(__file__).resolve().parents[1]
REPETITIONS = 20


def _prepare(path: Path) -> None:
    conn = connect(path)
    apply_migrations(conn)
    owner = setup_service.complete_setup(
        conn, setup_service.SetupData("duena", "Dueña", "clave123", "Romero", "V-1", "", "", D("5"))
    )
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    for i in range(6):
        product_service.create_product(
            conn,
            owner,
            ProductData(name=f"Repuesto {i}", price_usd=D("1.25") * (i + 1), cost_usd=D("0.5")),
            D("1000000"),
        )
    cash_service.open_session(conn, owner, D("100"), D("1000"))
    conn.close()


@pytest.mark.slow
def test_corte_de_luz_20_veces(tmp_path: Path) -> None:
    db = tmp_path / "corte.db"
    _prepare(db)
    rnd = random.Random(20261107)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)])}
    sales_seen = []
    for rep in range(REPETITIONS):
        proc = subprocess.Popen(
            [sys.executable, str(WORKER), str(db), str(rep)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=ROOT,
        )
        assert proc.stdout is not None
        line = proc.stdout.readline()
        assert line.strip() == b"ready", proc.stderr.read().decode(errors="replace") if proc.stderr else line
        time.sleep(rnd.uniform(0.05, 0.6))
        proc.kill()  # corte brusco, sin cerrar la conexión ni terminar la transacción
        proc.wait(timeout=10)
        assert proc.returncode != 0, "el subproceso terminó solo: revise el bucle de ventas"

        conn = connect(db)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", f"repetición {rep}"
            assert all_violations(conn) == [], f"repetición {rep}"
            sales_seen.append(conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0])
        finally:
            conn.close()
    assert sales_seen[-1] > REPETITIONS, f"se cobraron muy pocas ventas: {sales_seen}"
