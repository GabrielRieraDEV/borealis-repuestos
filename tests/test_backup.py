"""Fase 5 · respaldo (RF-90 a RF-92, RN-15): verificado, rotación de 30, nube, y restauración de ida y vuelta."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from repuestos.backup import files
from repuestos.config import Paths
from repuestos.db.connection import connect
from repuestos.db.migrate import apply_migrations
from repuestos.domain.sale import PaymentInput as P
from repuestos.domain.sale import PaymentMethod as M
from repuestos.services import (
    backup_service,
    cash_service,
    product_service,
    rate_service,
    sale_service,
    settings_service,
    setup_service,
)
from repuestos.services.sale_service import CartItem
from tests.helpers import as_seller, pastillas

NOW = datetime(2026, 11, 7, 18, 30)
TABLES = [
    "users", "audit_log", "categories", "products", "exchange_rates", "suppliers", "purchases", "purchase_items",
    "customers", "cash_sessions", "cash_movements", "sales", "sale_items", "receivables", "credit_payments",
    "credit_allocations", "payments", "inventory_movements", "monthly_snapshots", "settings", "doc_sequences",
    "schema_migrations",
]  # fmt: skip


@pytest.fixture
def store(tmp_path: Path):
    paths = Paths(tmp_path / "BorealisRepuestos")
    paths.ensure()
    conn = connect(paths.db_path)
    apply_migrations(conn)
    owner = setup_service.complete_setup(
        conn, setup_service.SetupData("duena", "Dueña", "clave123", "Romero", "V-1", "", "", D("5"))
    )
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    p = product_service.create_product(conn, owner, pastillas(conn), D("10"))
    cash_service.open_session(conn, owner, D("20"), D("500"))
    sale_service.charge(conn, owner, [CartItem(p.id, D("2"))], [P(M.POS, D("5780"))], D("231.0468"))
    yield paths, conn, owner, p
    conn.close()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def set_cloud(conn, owner, folder: Path | str) -> None:
    settings_service.save(conn, owner, replace(settings_service.load(conn), cloud_backup_dir=str(folder)))


# ------------------------------------------------------------------ respaldo


def test_respaldo_local_verificado(store) -> None:
    paths, conn, owner, _ = store
    assert backup_service.needs_backup(conn, NOW)
    result = backup_service.run_backup(paths, NOW)
    assert result.local == paths.backup_dir / "romero_20261107_1830.db"
    assert files.verify(result.local)
    assert result.cloud is None and result.cloud_error is None
    copy = sqlite3.connect(result.local)
    assert copy.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1
    copy.close()
    assert not backup_service.needs_backup(conn, NOW + timedelta(hours=11))
    assert backup_service.needs_backup(conn, NOW + timedelta(hours=13))  # más de 12 h (RF-90)


def test_respaldo_en_la_nube_con_pdfs(store, tmp_path) -> None:
    paths, conn, owner, _ = store
    cloud = tmp_path / "Google Drive" / "Respaldo Romero"
    set_cloud(conn, owner, cloud)
    result = backup_service.run_backup(paths, NOW, with_pdfs=True)
    assert result.cloud == cloud / "romero_20261107_1830.db" and files.verify(result.cloud)
    assert (cloud / "Inventario de hoy.pdf").exists() and (cloud / "Resumen del mes.pdf").exists()
    assert result.pdf_error is None
    st = backup_service.status(conn, NOW + timedelta(hours=47))
    assert st.cloud_configured and not st.cloud_stale and st.last_cloud == NOW
    assert backup_service.status(conn, NOW + timedelta(hours=49)).cloud_stale  # aviso a las 48 h


def test_si_falla_la_nube_el_respaldo_local_queda(store, tmp_path) -> None:
    paths, conn, owner, _ = store
    blocker = tmp_path / "no-es-carpeta.txt"
    blocker.write_text("x")
    set_cloud(conn, owner, blocker)
    result = backup_service.run_backup(paths, NOW)
    assert files.verify(result.local)
    assert result.cloud is None and "nube" in (result.cloud_error or "")
    st = backup_service.status(conn, NOW)
    assert st.last_local == NOW and st.last_cloud is None and st.cloud_stale


def test_rotacion_deja_30(store) -> None:
    paths, _, owner, _ = store
    for i in range(33):
        backup_service.run_backup(paths, NOW + timedelta(minutes=i))
    names = [p.name for p in backup_service.list_backups(paths)]
    assert len(names) == 30
    assert names[0] == "romero_20261107_1902.db" and names[-1] == "romero_20261107_1833.db"


def test_verificacion_detecta_archivo_danado(store, tmp_path) -> None:
    paths, *_ = store
    bad = tmp_path / "romero_20261107_1830.db"
    bad.write_bytes(b"esto no es una base de datos" * 100)
    assert not files.verify(bad)
    with pytest.raises(files.BackupError):
        files.replace_database(bad, paths.db_path)
    assert files.verify(paths.db_path)


# ------------------------------------------------------------------ restaurar (RF-91)


def test_restauracion_de_ida_y_vuelta(store) -> None:
    paths, conn, owner, product = store
    before = counts(conn)
    backup = backup_service.run_backup(paths, NOW).local
    # después del respaldo se siguen haciendo cosas
    sale_service.charge(conn, owner, [CartItem(product.id, D("1"))], [P(M.POS, D("2890"))], D("231.0468"))
    product_service.create_product(conn, owner, pastillas(conn, name="Otro"), D("1"))
    changed = counts(conn)
    assert changed != before
    conn.close()  # modo exclusivo: ninguna conexión abierta

    previous = backup_service.restore(paths, owner, backup, NOW + timedelta(hours=1))
    assert previous.name == "romero_20261107_1930_antes_de_restaurar.db"
    restored = connect(paths.db_path)
    try:
        after = counts(restored)
        assert {t: after[t] for t in TABLES if t != "audit_log"} == {t: before[t] for t in TABLES if t != "audit_log"}
        assert after["audit_log"] == before["audit_log"] + 1  # queda en bitácora (RN-16)
        assert (
            restored.execute("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()[0] == "BACKUP_RESTORED"
        )
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        restored.close()
    prev = sqlite3.connect(previous)
    assert prev.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == changed["sales"]  # nada se perdió
    prev.close()
    assert previous in backup_service.list_backups(paths)


def test_solo_la_duena_restaura(store) -> None:
    paths, conn, owner, _ = store
    backup = backup_service.run_backup(paths, NOW).local
    with pytest.raises(PermissionError):
        backup_service.check_can_restore(as_seller(owner), backup)
    with pytest.raises(LookupError):
        backup_service.check_can_restore(owner, paths.backup_dir / "no-existe.db")


def test_foto_mensual_en_respaldo_no_interfiere(store) -> None:
    paths, conn, *_ = store
    from repuestos.services import report_service

    assert report_service.ensure_monthly_snapshot(conn, date(2026, 12, 1)) == "2026-11"
    assert files.verify(backup_service.run_backup(paths, NOW).local)
