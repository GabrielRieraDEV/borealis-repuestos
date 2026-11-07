"""Log técnico rotativo (RNF-07): 5 archivos de 1 MB. Sin datos de clientes ni contraseñas."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_BYTES = 1_000_000
BACKUP_COUNT = 4  # el archivo activo + 4 rotados = 5 archivos


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "repuestos.log", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    for old in [h for h in root.handlers if isinstance(h, RotatingFileHandler)]:
        root.removeHandler(old)
        old.close()
    root.addHandler(handler)
