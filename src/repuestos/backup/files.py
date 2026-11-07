"""Archivos de respaldo (RN-15): copia con la API de respaldo de SQLite, verificación y rotación."""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

KEEP = 30
_ROTATING = re.compile(r"^romero_\d{8}_\d{4}\.db$")
_ANY = re.compile(r"^romero_\d{8}_\d{4}(_antes_de_restaurar)?\.db$")


class BackupError(Exception):
    """El respaldo no se pudo crear o no pasó la verificación."""


def backup_name(now: datetime, suffix: str = "") -> str:
    return f"romero_{now:%Y%m%d_%H%M}{suffix}.db"


def verify(path: Path) -> bool:
    """PRAGMA integrity_check sobre la copia."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def _copy_once(db_path: Path, target: Path) -> None:
    # nombre temporal único: dos respaldos al mismo tiempo nunca escriben el mismo archivo
    tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)  # copia consistente aunque haya escrituras (incluye lo que está en el WAL)
        finally:
            dst.close()
    finally:
        src.close()
    if not verify(tmp):
        tmp.unlink(missing_ok=True)
        raise BackupError("La copia no pasó la verificación de integridad.")
    os.replace(tmp, target)


def make_backup(db_path: Path, dest_dir: Path, now: datetime, suffix: str = "") -> Path:
    """Crea y verifica la copia. Si la verificación falla, la borra y reintenta una vez (RN-15)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / backup_name(now, suffix)
    try:
        _copy_once(db_path, target)
    except (BackupError, sqlite3.Error, OSError) as first:
        log.warning("Respaldo falló, se reintenta una vez: %s", first)
        try:
            _copy_once(db_path, target)
        except (BackupError, sqlite3.Error, OSError) as second:
            raise BackupError(f"No se pudo crear el respaldo: {second}") from second
    return target


def copy_to(backup: Path, folder: Path) -> Path:
    """Copia el respaldo a otra carpeta (la de la nube) y verifica la copia."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / backup.name
    tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    shutil.copy2(backup, tmp)
    if tmp.stat().st_size != backup.stat().st_size or not verify(tmp):
        tmp.unlink(missing_ok=True)
        raise BackupError("La copia en la carpeta de la nube no pasó la verificación.")
    os.replace(tmp, target)
    return target


def rotate(folder: Path, keep: int = KEEP) -> list[Path]:
    """Deja los ``keep`` respaldos automáticos más recientes. Los «antes de restaurar» no se borran."""
    if not folder.exists():
        return []
    files = sorted((p for p in folder.iterdir() if _ROTATING.match(p.name)), key=lambda p: p.name, reverse=True)
    removed = []
    for old in files[keep:]:
        try:
            old.unlink()
            removed.append(old)
        except OSError as exc:
            log.warning("No se pudo borrar el respaldo viejo %s: %s", old, exc)
    return removed


def list_backups(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted((p for p in folder.iterdir() if _ANY.match(p.name)), key=lambda p: p.name, reverse=True)


def replace_database(backup: Path, db_path: Path) -> None:
    """Reemplaza la base por el respaldo. Todas las conexiones deben estar cerradas.

    Se borran los -wal y -shm viejos: si quedaran, SQLite los aplicaría sobre la base restaurada.
    """
    tmp = db_path.with_name(db_path.name + ".restaurando")
    shutil.copy2(backup, tmp)
    if not verify(tmp):
        tmp.unlink(missing_ok=True)
        raise BackupError("El respaldo elegido está dañado: no se restauró nada.")
    for extra in (db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
        extra.unlink(missing_ok=True)
    os.replace(tmp, db_path)
