"""Asistente de primer arranque (RF-02): crea la dueña y guarda los datos del negocio."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import settings as settings_repo
from repuestos.db.repositories import users as users_repo
from repuestos.domain.passwords import hash_password, validate_new_password
from repuestos.domain.users import Role, User
from repuestos.services.audit_service import audit


@dataclass(frozen=True, slots=True)
class SetupData:
    owner_username: str
    owner_full_name: str
    password: str
    business_name: str
    business_rif: str
    business_address: str
    business_phone: str
    rounding_multiple: Decimal
    printer_name: str = ""
    cloud_backup_dir: str = ""


def needs_setup(conn: sqlite3.Connection) -> bool:
    return users_repo.count(conn) == 0


def validate(data: SetupData) -> None:
    if not data.owner_username.strip():
        raise ValueError("Escriba un nombre de usuario para la dueña.")
    if not data.owner_full_name.strip():
        raise ValueError("Escriba el nombre completo de la dueña.")
    validate_new_password(data.password)
    if not data.business_name.strip():
        raise ValueError("Escriba la razón social del negocio.")
    if not data.business_rif.strip():
        raise ValueError("Escriba el RIF del negocio.")
    if data.rounding_multiple <= 0:
        raise ValueError("El múltiplo de redondeo debe ser mayor que cero (por ejemplo 5,00).")
    if data.rounding_multiple != data.rounding_multiple.quantize(Decimal("0.01")):
        raise ValueError("El múltiplo de redondeo admite como máximo 2 decimales.")


def complete_setup(conn: sqlite3.Connection, data: SetupData) -> User:
    validate(data)
    with transaction(conn):
        if users_repo.count(conn) != 0:
            raise RuntimeError("El sistema ya fue configurado.")
        user_id = users_repo.insert(
            conn,
            data.owner_username.strip(),
            data.owner_full_name.strip(),
            Role.OWNER,
            hash_password(data.password),
        )
        values = {
            "business_name": data.business_name.strip(),
            "business_rif": data.business_rif.strip().upper(),
            "business_address": data.business_address.strip(),
            "business_phone": data.business_phone.strip(),
            "printer_name": data.printer_name.strip(),
            "cloud_backup_dir": data.cloud_backup_dir.strip(),
        }
        for key, value in values.items():
            settings_repo.set_value(conn, key, value)
        settings_repo.set_decimal(conn, "rounding_multiple_e2", data.rounding_multiple, "e2")
        audit(conn, user_id, "USER_CREATED", "user", user_id, {"username": data.owner_username, "role": "owner"})
        details = {**values, "rounding_multiple": data.rounding_multiple}
        audit(conn, user_id, "SETUP_COMPLETED", "settings", None, details)
    user = users_repo.get(conn, user_id)
    assert user is not None
    return user
