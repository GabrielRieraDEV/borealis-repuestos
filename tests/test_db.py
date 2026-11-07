import sqlite3
from pathlib import Path

import pytest

from repuestos.db.connection import connect, transaction
from repuestos.db.migrate import Migration, applied_versions, apply_migrations, load_migrations

ROOT = Path(__file__).resolve().parents[1]


def test_migration_0001_is_exact_copy_of_schema_sql() -> None:
    m = load_migrations()[0]
    assert m.version == 1
    assert m.sql == (ROOT / "docs" / "schema.sql").read_text(encoding="utf-8")


def test_pragmas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_migrations_applied_once(conn: sqlite3.Connection) -> None:
    assert applied_versions(conn) == {1, 2}
    assert apply_migrations(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 10
    assert conn.execute("SELECT next_number FROM doc_sequences WHERE doc_type = 'R'").fetchone()[0] == 1


def test_failed_migration_rolls_back_and_is_not_recorded(conn: sqlite3.Connection) -> None:
    bad = Migration(99, "0099_mala.sql", "CREATE TABLE t_ok (x INTEGER);\nINSERT INTO tabla_que_no_existe VALUES (1);")
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(conn, [*load_migrations(), bad])
    assert not conn.in_transaction
    assert applied_versions(conn) == {1, 2}
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 't_ok'").fetchone() is None


def test_transaction_commits(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        conn.execute("UPDATE settings SET value = 'X' WHERE key = 'business_name'")
    assert conn.execute("SELECT value FROM settings WHERE key = 'business_name'").fetchone()[0] == "X"


def test_transaction_rolls_back_on_error(conn: sqlite3.Connection) -> None:
    with pytest.raises(ZeroDivisionError), transaction(conn):
        conn.execute("UPDATE settings SET value = 'X' WHERE key = 'business_name'")
        _ = 1 / 0
    assert not conn.in_transaction
    assert conn.execute("SELECT value FROM settings WHERE key = 'business_name'").fetchone()[0] == ""


def test_nested_transaction_is_rejected(conn: sqlite3.Connection) -> None:
    with transaction(conn), pytest.raises(RuntimeError), transaction(conn):
        pass


def test_foreign_keys_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError), transaction(conn):
        conn.execute("INSERT INTO audit_log (user_id, action) VALUES (999, 'X')")


def test_reopen_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "r.db"
    c1 = connect(path)
    apply_migrations(c1)
    c1.close()
    c2 = connect(path)
    assert apply_migrations(c2) == []
    assert c2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    c2.close()
