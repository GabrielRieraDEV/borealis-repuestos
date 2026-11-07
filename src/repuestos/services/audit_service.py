"""Servicio de bitácora (RN-16, RF-05).

Se llama dentro de la transacción del caso de uso, con la misma conexión: si la operación se revierte,
su registro en la bitácora también.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Any

from repuestos.db.repositories import audit as audit_repo


def _default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"no se puede guardar {type(value).__name__} en la bitácora")


def audit(
    conn: sqlite3.Connection,
    user_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
    authorized_by: int | None = None,
) -> int:
    if not conn.in_transaction:
        raise RuntimeError("audit() debe llamarse dentro de la transacción de la operación")
    details_json = (
        json.dumps(details, ensure_ascii=False, sort_keys=True, default=_default) if details else None
    )
    return audit_repo.insert(conn, user_id, action, entity, entity_id, details_json, authorized_by)
