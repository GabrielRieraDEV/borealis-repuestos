"""Respaldo y restauración (RF-90 a RF-92, RN-15).

``run_backup`` abre su propia conexión: se puede llamar desde un hilo de fondo sin tocar la de la pantalla.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from repuestos.backup import files
from repuestos.config import Paths
from repuestos.db.connection import connect, transaction
from repuestos.db.migrate import apply_migrations
from repuestos.db.repositories import settings as settings_repo
from repuestos.db.repositories import users as users_repo
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit

log = logging.getLogger(__name__)

TIME_FMT = "%Y-%m-%d %H:%M:%S"
AUTO_EVERY = timedelta(hours=12)  # al arrancar, si el último tiene más de 12 h (RF-90)
CLOUD_STALE = timedelta(hours=48)  # aviso en la barra (RF-90)

BackupError = files.BackupError


@dataclass(frozen=True, slots=True)
class BackupResult:
    local: Path
    cloud: Path | None
    cloud_error: str | None
    pdf_error: str | None


def _parse(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, TIME_FMT) if text else None
    except ValueError:
        return None


def run_backup(paths: Paths, now: datetime | None = None, with_pdfs: bool = False) -> BackupResult:
    """Respaldo local (verificado, 30 copias) + copia a la carpeta de la nube (30 copias) + PDF de la nube (RF-92).

    Una falla de la nube no anula el respaldo local: se informa en ``cloud_error``.
    """
    now = now or datetime.now()
    conn = connect(paths.db_path)
    try:
        cloud_dir = settings_repo.get(conn, "cloud_backup_dir").strip()
        local = files.make_backup(paths.db_path, paths.backup_dir, now)
        files.rotate(paths.backup_dir)
        with transaction(conn):
            settings_repo.set_value(conn, "last_backup_at", now.strftime(TIME_FMT))
        cloud = cloud_error = pdf_error = None
        if cloud_dir:
            folder = Path(cloud_dir)
            try:
                cloud = files.copy_to(local, folder)
                files.rotate(folder)
                with transaction(conn):
                    settings_repo.set_value(conn, "last_cloud_backup_at", now.strftime(TIME_FMT))
            except (OSError, files.BackupError) as exc:
                log.warning("No se pudo copiar el respaldo a la nube (%s): %s", folder, exc)
                cloud_error = (
                    "No se pudo copiar el respaldo a la carpeta de la nube. "
                    "Revise que Google Drive esté abierto y que la carpeta exista (Configuración)."
                )
            if with_pdfs:
                try:
                    from repuestos.services import print_service

                    print_service.cloud_pdfs(conn, folder)
                except Exception as exc:  # los PDF son un extra (RF-92 «d»): nunca tumban el respaldo
                    log.exception("No se pudieron generar los PDF de la nube")
                    pdf_error = str(exc)
        log.info("Respaldo creado: %s (nube: %s)", local.name, cloud or cloud_error or "no configurada")
        return BackupResult(local, cloud, cloud_error, pdf_error)
    finally:
        conn.close()


def needs_backup(conn: sqlite3.Connection, now: datetime | None = None) -> bool:
    last = _parse(settings_repo.get(conn, "last_backup_at"))
    return last is None or (now or datetime.now()) - last > AUTO_EVERY


@dataclass(frozen=True, slots=True)
class BackupStatus:
    last_local: datetime | None
    last_cloud: datetime | None
    cloud_configured: bool
    cloud_stale: bool  # más de 48 h sin copia en la nube (o nunca)


def status(conn: sqlite3.Connection, now: datetime | None = None) -> BackupStatus:
    now = now or datetime.now()
    last_cloud = _parse(settings_repo.get(conn, "last_cloud_backup_at"))
    configured = bool(settings_repo.get(conn, "cloud_backup_dir").strip())
    return BackupStatus(
        last_local=_parse(settings_repo.get(conn, "last_backup_at")),
        last_cloud=last_cloud,
        cloud_configured=configured,
        cloud_stale=last_cloud is None or now - last_cloud > CLOUD_STALE,
    )


def list_backups(paths: Paths) -> list[Path]:
    return files.list_backups(paths.backup_dir)


def check_can_restore(user: User, backup: Path) -> None:
    require_owner(user, "restaurar un respaldo")
    if not backup.exists():
        raise LookupError("El archivo de respaldo no existe.")
    if not files.verify(backup):
        raise ValueError("Ese respaldo está dañado (no pasa la verificación). Elija otro.")


def restore(paths: Paths, user: User, backup: Path, now: datetime | None = None) -> Path:
    """RF-91 / RN-15. Antes de llamarla hay que cerrar TODAS las conexiones a la base (modo exclusivo).

    1. Respalda el estado actual con sufijo ``_antes_de_restaurar``.
    2. Reemplaza la base por el respaldo (verificado).
    3. Aplica migraciones pendientes (por si el respaldo es de una versión anterior) y deja constancia en la bitácora.
    Devuelve la ruta de la copia previa. Después, el programa se reinicia.
    """
    check_can_restore(user, backup)
    now = now or datetime.now()
    before = files.make_backup(paths.db_path, paths.backup_dir, now, suffix="_antes_de_restaurar")
    files.replace_database(backup, paths.db_path)
    conn = connect(paths.db_path)
    try:
        apply_migrations(conn)
        with transaction(conn):
            actor = users_repo.get(conn, user.id)
            audit(
                conn,
                user.id if actor is not None else None,
                "BACKUP_RESTORED",
                "backup",
                None,
                {"respaldo": backup.name, "copia_previa": before.name, "usuario": user.username},
            )
    finally:
        conn.close()
    log.warning("Base restaurada desde %s (copia previa %s)", backup, before)
    return before
