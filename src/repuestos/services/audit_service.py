"""Servicio de bitácora (RN-16, RF-05).

Se llama dentro de la transacción del caso de uso, con la misma conexión: si la operación se revierte,
su registro en la bitácora también.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

from repuestos.db.repositories import audit as audit_repo
from repuestos.domain.users import User, require_owner


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
    details_json = json.dumps(details, ensure_ascii=False, sort_keys=True, default=_default) if details else None
    return audit_repo.insert(conn, user_id, action, entity, entity_id, details_json, authorized_by)


# ------------------------------------------------------------------ consulta (RF-05)

ACTION_LABELS = {
    "LOGIN": "Inicio de sesión",
    "LOGOUT": "Cierre de sesión",
    "LOGIN_FAILED": "Intento fallido de entrar",
    "USER_LOCKED": "Usuario bloqueado",
    "USER_CREATED": "Usuario creado",
    "USER_ACTIVATED": "Usuario activado",
    "USER_DEACTIVATED": "Usuario desactivado",
    "USER_PASSWORD_RESET": "Contraseña restablecida",
    "SETUP_COMPLETED": "Configuración inicial",
    "SETTINGS_CHANGED": "Configuración cambiada",
    "AUTHORIZATION_FAILED": "Clave de la dueña incorrecta",
    "PRODUCT_CREATED": "Producto creado",
    "PRODUCT_UPDATED": "Producto editado",
    "PRODUCT_ACTIVATED": "Producto activado",
    "PRODUCT_DEACTIVATED": "Producto desactivado",
    "PRICE_CHANGE": "Cambio de precio",
    "COST_CHANGE": "Cambio de costo",
    "CATEGORY_CREATED": "Categoría creada",
    "CATEGORY_RENAMED": "Categoría renombrada",
    "CATEGORY_ACTIVATED": "Categoría activada",
    "CATEGORY_DEACTIVATED": "Categoría desactivada",
    "RATE_MANUAL": "Tasa cargada a mano",
    "SUPPLIER_CREATED": "Proveedor creado",
    "PURCHASE_CREATED": "Compra registrada",
    "PURCHASE_VOID": "Compra anulada",
    "ADJUSTMENT": "Ajuste de inventario",
    "STOCK_COUNT": "Conteo físico",
    "STOCK_MISMATCH": "Existencias que no cuadran",
    "CASH_OPEN": "Apertura de caja",
    "CASH_CLOSE": "Cierre de caja",
    "CASH_IN": "Entrada de efectivo",
    "CASH_OUT": "Salida de efectivo",
    "SALE_VOID": "Venta anulada",
    "SALE_WITHOUT_STOCK": "Venta sin existencia",
    "CUSTOMER_CREATED": "Cliente creado",
    "CUSTOMER_UPDATED": "Cliente editado",
    "CUSTOMER_CREDIT_CHANGED": "Fiado del cliente cambiado",
    "CREDIT_LIMIT_EXCEEDED": "Fiado por encima del límite",
    "CREDIT_PAYMENT_VOID": "Abono anulado",
    "BACKUP_RESTORED": "Respaldo restaurado",
    "RECOVERY_CODE_CREATED": "Código de recuperación generado",
    "RECOVERY_FAILED": "Código de recuperación incorrecto",
    "OWNER_PASSWORD_RECOVERED": "Clave de la dueña recuperada con su código",
    "OWNER_PASSWORD_RESET_SUPPORT": "Clave de la dueña restablecida por soporte",
}


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def list_entries(
    conn: sqlite3.Connection,
    user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    action: str | None = None,
) -> list[audit_repo.AuditEntry]:
    """RF-05: bitácora con filtro por fecha, usuario y acción. Solo la dueña."""
    require_owner(user, "ver la bitácora")
    return audit_repo.search(conn, date_from, date_to, user_id, action)


def known_actions(conn: sqlite3.Connection) -> list[str]:
    return audit_repo.actions(conn)
