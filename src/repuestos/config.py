"""Rutas de datos (RNF-06).

Producción: ``C:\\ProgramData\\BorealisRepuestos\\{datos,respaldos,logs}``.
Desarrollo y pruebas: la variable de entorno ``REPUESTOS_DATA_DIR`` reemplaza la carpeta base
``C:\\ProgramData\\BorealisRepuestos``; dentro se crean las mismas subcarpetas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Borealis Repuestos"
DB_FILENAME = "romero.db"
ENV_DATA_DIR = "REPUESTOS_DATA_DIR"


def _default_base_dir() -> Path:
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(program_data) / "BorealisRepuestos"


@dataclass(frozen=True, slots=True)
class Paths:
    base: Path

    @property
    def data_dir(self) -> Path:
        return self.base / "datos"

    @property
    def backup_dir(self) -> Path:
        return self.base / "respaldos"

    @property
    def log_dir(self) -> Path:
        return self.base / "logs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    def ensure(self) -> None:
        for d in (self.data_dir, self.backup_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


def get_paths() -> Paths:
    override = os.environ.get(ENV_DATA_DIR)
    return Paths(Path(override) if override else _default_base_dir())
