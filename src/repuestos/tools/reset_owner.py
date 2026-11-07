"""Último recurso de soporte: poner una clave nueva a la dueña cuando perdió la clave Y el código de recuperación.

Solo para Borealis, con acceso a la PC. No viene en el instalador: se corre desde el código fuente.

    python -m repuestos.tools.reset_owner --db "C:\\ProgramData\\BorealisRepuestos\\datos\\romero.db"

Pide la clave nueva sin mostrarla, la guarda, quita el bloqueo, genera un código de recuperación nuevo y deja todo
en la bitácora (``OWNER_PASSWORD_RESET_SUPPORT``). Cierre el programa antes de usarlo.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from repuestos.db.connection import connect, transaction
from repuestos.db.migrate import apply_migrations
from repuestos.db.repositories import users as users_repo
from repuestos.domain.passwords import hash_password, validate_new_password
from repuestos.services import recovery_service
from repuestos.services.audit_service import audit


def reset(db: Path, new_password: str) -> str:
    """Devuelve el código de recuperación nuevo."""
    validate_new_password(new_password)
    conn = connect(db)
    try:
        apply_migrations(conn)
        owners = [u for u in users_repo.list_all(conn) if u.is_owner and u.active]
        if not owners:
            raise SystemExit("No hay una dueña activa en esta base.")
        owner = owners[0]
        with transaction(conn):
            users_repo.set_password_hash(conn, owner.id, hash_password(new_password))
            code = recovery_service.store_new_code(conn)
            audit(conn, None, "OWNER_PASSWORD_RESET_SUPPORT", "user", owner.id, {"usuario": owner.username})
        return code
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True, help="ruta de romero.db")
    args = parser.parse_args()
    if not args.db.exists():
        print(f"No existe {args.db}")
        return 2
    first = getpass.getpass("Clave nueva de la dueña: ")
    if first != getpass.getpass("Repítala: "):
        print("Las claves no coinciden.")
        return 1
    try:
        code = reset(args.db, first)
    except ValueError as exc:
        print(exc)
        return 1
    print(f"Listo. Código de recuperación nuevo (entréguelo a la dueña): {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
