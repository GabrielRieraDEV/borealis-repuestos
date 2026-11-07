"""Tasa vigente, carga manual y guardado de la tasa del BCV (RN-01, RF-20 a RF-22)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import exchange_rates as repo
from repuestos.db.repositories.exchange_rates import ExchangeRate, RateSource
from repuestos.domain.money import hu
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit

STALE_AFTER_DAYS = 3
SOURCE_LABELS = {RateSource.BCV_AUTO: "BCV automática", RateSource.MANUAL: "manual"}


@dataclass(frozen=True, slots=True)
class CurrentRate:
    rate: Decimal
    valid_date: date
    source: RateSource
    stale: bool  # más de 3 días: aviso amarillo, pero se puede vender


def current_rate(conn: sqlite3.Connection, today: date | None = None) -> CurrentRate | None:
    """RN-01: la de fecha valor más reciente que sea <= hoy. None si no hay ninguna (no se puede vender)."""
    today = today or date.today()
    r = repo.current(conn, today)
    if r is None:
        return None
    return CurrentRate(r.rate, r.valid_date, r.source, (today - r.valid_date).days > STALE_AFTER_DAYS)


def require_rate(conn: sqlite3.Connection, today: date | None = None) -> CurrentRate:
    rate = current_rate(conn, today)
    if rate is None:
        raise LookupError("No hay tasa del día. Cárguela en Tasa BCV.")
    return rate


def _check_rate(rate: Decimal) -> Decimal:
    if rate <= 0:
        raise ValueError("La tasa debe ser mayor que cero.")
    if rate != hu(rate, 6):
        raise ValueError("La tasa admite como máximo 6 decimales.")
    return rate


def set_manual_rate(conn: sqlite3.Connection, user: User, rate: Decimal, today: date | None = None) -> None:
    """RN-01: la dueña escribe la tasa; fecha valor = hoy, origen MANUAL. Reemplaza la de hoy y deja la anterior
    en bitácora."""
    require_owner(user, "cargar la tasa a mano")
    _check_rate(rate)
    today = today or date.today()
    with transaction(conn):
        existing = repo.get_by_date(conn, today)
        details: dict[str, object] = {"fecha_valor": today.isoformat(), "tasa": rate}
        if existing is None:
            rate_id = repo.insert(conn, today, rate, RateSource.MANUAL, user.id)
        else:
            rate_id = existing.id
            details |= {"tasa_anterior": existing.rate, "origen_anterior": existing.source.value}
            repo.replace(conn, existing.id, rate, RateSource.MANUAL, user.id)
        audit(conn, user.id, "RATE_MANUAL", "exchange_rate", rate_id, details)


def save_bcv_rate(conn: sqlite3.Connection, rate: Decimal, valid_date: date) -> bool:
    """Guarda la tasa descargada. Devuelve True si cambió algo.

    - Si no hay tasa para esa fecha valor, la inserta.
    - Si ya hay una automática con otro valor (corrección del BCV), la actualiza.
    - Si ya hay una MANUAL para esa fecha, no la toca: manda lo que cargó la dueña.
    """
    _check_rate(rate)
    with transaction(conn):
        existing: ExchangeRate | None = repo.get_by_date(conn, valid_date)
        if existing is None:
            repo.insert(conn, valid_date, rate, RateSource.BCV_AUTO, None)
            return True
        if existing.source is RateSource.BCV_AUTO and existing.rate != rate:
            repo.replace(conn, existing.id, rate, RateSource.BCV_AUTO, None)
            return True
        return False


def recent_rates(conn: sqlite3.Connection, limit: int = 20) -> list[ExchangeRate]:
    return repo.recent(conn, limit)
