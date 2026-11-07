"""Configuración del negocio (RF-06), tipada sobre la tabla clave-valor ``settings``."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, fields
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import settings as repo
from repuestos.domain.money import hu
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit


@dataclass(frozen=True, slots=True)
class AppSettings:
    business_name: str
    business_rif: str
    business_address: str
    business_phone: str
    rounding_multiple: Decimal  # Bs (RN-03)
    default_min_stock: Decimal  # unidades (RN-10)
    default_credit_days: int  # RN-07
    allow_negative_stock: bool  # RN-09
    payment_usdt_enabled: bool  # RN-06
    igtf_percent: Decimal  # sin lógica en esta fase
    printer_name: str
    cloud_backup_dir: str
    large_font: bool


def load(conn: sqlite3.Connection) -> AppSettings:
    raw = repo.get_all(conn)
    return AppSettings(
        business_name=raw["business_name"],
        business_rif=raw["business_rif"],
        business_address=raw["business_address"],
        business_phone=raw["business_phone"],
        rounding_multiple=repo.get_decimal(conn, "rounding_multiple_e2", "e2"),
        default_min_stock=repo.get_decimal(conn, "default_min_stock_e3", "e3"),
        default_credit_days=int(raw["default_credit_days"]),
        allow_negative_stock=raw["allow_negative_stock"] == "1",
        payment_usdt_enabled=raw["payment_usdt_enabled"] == "1",
        igtf_percent=repo.get_decimal(conn, "igtf_bp", "bp"),
        printer_name=raw["printer_name"],
        cloud_backup_dir=raw["cloud_backup_dir"],
        large_font=raw["large_font"] == "1",
    )


def validate(s: AppSettings) -> None:
    if not s.business_name.strip():
        raise ValueError("Escriba la razón social del negocio.")
    if not s.business_rif.strip():
        raise ValueError("Escriba el RIF del negocio.")
    if s.rounding_multiple <= 0 or s.rounding_multiple != hu(s.rounding_multiple, 2):
        raise ValueError("El múltiplo de redondeo debe ser mayor que cero y tener como máximo 2 decimales.")
    if s.default_min_stock < 0 or s.default_min_stock != hu(s.default_min_stock, 3):
        raise ValueError("El mínimo por defecto no puede ser negativo y admite como máximo 3 decimales.")
    if s.default_credit_days <= 0:
        raise ValueError("El plazo de fiado debe ser de al menos 1 día.")
    if s.igtf_percent < 0 or s.igtf_percent != hu(s.igtf_percent, 2):
        raise ValueError("El IGTF no puede ser negativo y admite como máximo 2 decimales.")


def save(conn: sqlite3.Connection, user: User, new: AppSettings) -> None:
    require_owner(user, "cambiar la configuración")
    validate(new)
    with transaction(conn):
        old = load(conn)
        changes = {
            f.name: {"antes": getattr(old, f.name), "despues": getattr(new, f.name)}
            for f in fields(AppSettings)
            if getattr(old, f.name) != getattr(new, f.name)
        }
        if not changes:
            return
        text = {k: v for k, v in asdict(new).items() if isinstance(v, str)}
        for key, value in text.items():
            repo.set_value(conn, key, value.strip() if key != "cloud_backup_dir" else value)
        repo.set_value(conn, "business_rif", new.business_rif.strip().upper())
        repo.set_decimal(conn, "rounding_multiple_e2", new.rounding_multiple, "e2")
        repo.set_decimal(conn, "default_min_stock_e3", new.default_min_stock, "e3")
        repo.set_value(conn, "default_credit_days", str(new.default_credit_days))
        repo.set_value(conn, "allow_negative_stock", "1" if new.allow_negative_stock else "0")
        repo.set_value(conn, "payment_usdt_enabled", "1" if new.payment_usdt_enabled else "0")
        repo.set_decimal(conn, "igtf_bp", new.igtf_percent, "bp")
        repo.set_value(conn, "large_font", "1" if new.large_font else "0")
        audit(conn, user.id, "SETTINGS_CHANGED", "settings", None, changes)
