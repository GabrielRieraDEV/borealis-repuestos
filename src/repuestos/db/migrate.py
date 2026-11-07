"""Runner de migraciones.

Aplica en orden los ``db/migrations/NNNN_descripcion.sql`` pendientes, cada uno en su propia transacción,
y registra la versión en ``schema_migrations``. Nunca editar una migración publicada: crear una nueva.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from importlib import resources

log = logging.getLogger(__name__)

_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def load_migrations() -> list[Migration]:
    found: dict[int, Migration] = {}
    for entry in resources.files("repuestos.db.migrations").iterdir():
        match = _NAME.match(entry.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in found:
            raise RuntimeError(f"Migración duplicada con versión {version}: {entry.name}")
        found[version] = Migration(version, entry.name, entry.read_text(encoding="utf-8"))
    return [found[v] for v in sorted(found)]


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'").fetchone()
    if not exists:
        return set()
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def apply_migrations(conn: sqlite3.Connection, migrations: list[Migration] | None = None) -> list[int]:
    """Aplica las migraciones pendientes. Devuelve las versiones aplicadas en esta llamada."""
    if conn.in_transaction:
        raise RuntimeError("apply_migrations necesita una conexión sin transacción abierta")
    migrations = load_migrations() if migrations is None else migrations
    done = applied_versions(conn)
    applied: list[int] = []
    for m in migrations:
        if m.version in done:
            continue
        log.info("Aplicando migración %s", m.name)
        script = f"BEGIN IMMEDIATE;\n{m.sql}\n;INSERT INTO schema_migrations (version) VALUES ({m.version});\nCOMMIT;"
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            log.exception("Falló la migración %s", m.name)
            raise
        applied.append(m.version)
    return applied
