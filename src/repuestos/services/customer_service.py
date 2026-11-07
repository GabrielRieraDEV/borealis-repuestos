"""Clientes (RF-51): "Consumidor final" por defecto; buscar o crear por cédula/RIF y nombre."""

from __future__ import annotations

import re
import sqlite3

from repuestos.db.connection import transaction
from repuestos.db.repositories import customers as repo
from repuestos.db.repositories.customers import FINAL_CONSUMER_ID, Customer
from repuestos.domain.users import User
from repuestos.services.audit_service import audit

_ID_DOC = re.compile(r"^([VEJGP])(\d{5,10})$")


def normalize_id_doc(text: str) -> str:
    """'V-12.345.678' → 'V12345678'. Solo números → se asume cédula venezolana (V)."""
    raw = re.sub(r"[^0-9A-Za-z]", "", text).upper()
    if raw.isdigit():
        raw = "V" + raw
    if not _ID_DOC.match(raw):
        raise ValueError("Cédula o RIF inválido. Ejemplos: V12345678, E8123456, J123456789.")
    return raw


def format_id_doc(id_doc: str | None) -> str:
    if not id_doc:
        return ""
    return f"{id_doc[0]}-{id_doc[1:]}"


def final_consumer(conn: sqlite3.Connection) -> Customer:
    c = repo.get(conn, FINAL_CONSUMER_ID)
    assert c is not None
    return c


def get(conn: sqlite3.Connection, customer_id: int) -> Customer:
    c = repo.get(conn, customer_id)
    if c is None:
        raise LookupError("El cliente no existe.")
    return c


def search(conn: sqlite3.Connection, text: str) -> list[Customer]:
    text = text.strip()
    if not text:
        return []
    try:
        exact = repo.get_by_id_doc(conn, normalize_id_doc(text))
    except ValueError:
        exact = None
    results = repo.search(conn, text)
    if exact is not None:
        results = [exact, *[c for c in results if c.id != exact.id]]
    return results


def find_by_id_doc(conn: sqlite3.Connection, text: str) -> Customer | None:
    return repo.get_by_id_doc(conn, normalize_id_doc(text))


def create(conn: sqlite3.Connection, user: User, name: str, id_doc: str, phone: str = "") -> Customer:
    """Cualquier usuario puede crear clientes al vender (P44)."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("Escriba el nombre del cliente.")
    doc = normalize_id_doc(id_doc)
    with transaction(conn):
        existing = repo.get_by_id_doc(conn, doc)
        if existing is not None:
            raise ValueError(f"Ya existe el cliente {existing.name} con {format_id_doc(doc)}.")
        customer_id = repo.insert(conn, name, doc, phone.strip())
        audit(conn, user.id, "CUSTOMER_CREATED", "customer", customer_id, {"nombre": name, "documento": doc})
    return get(conn, customer_id)
