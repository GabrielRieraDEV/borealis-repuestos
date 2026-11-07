from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from repuestos.db.connection import connect
from repuestos.db.migrate import apply_migrations
from repuestos.services import setup_service


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "test.db")
    apply_migrations(c)
    yield c
    c.close()


OWNER_PASSWORD = "clave123"


@pytest.fixture
def owner(conn: sqlite3.Connection):
    return setup_service.complete_setup(
        conn,
        setup_service.SetupData(
            owner_username="yoleida",
            owner_full_name="Yoleida Romero",
            password=OWNER_PASSWORD,
            business_name="PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P.",
            business_rif="v-31463591-0",
            business_address="Ciudad Bolívar",
            business_phone="0285-0000000",
            rounding_multiple=Decimal("5.00"),
        ),
    )
