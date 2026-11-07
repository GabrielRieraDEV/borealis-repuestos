"""Caja (RF-60 a RF-63, RN-11): apertura, entradas y salidas, cierre ciego e historial.

Una sola sesión abierta. Si el programa se cierra con la caja abierta, al volver sigue la misma.
El vendedor no ve lo esperado ni la diferencia: la UI lo oculta y el servicio lo niega.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal

from repuestos.db.connection import transaction
from repuestos.db.repositories import cash as repo
from repuestos.db.repositories.cash import CashMovement, CashSession
from repuestos.domain.cash import cash_difference, expected_cash
from repuestos.domain.money import hu
from repuestos.domain.sale import NON_CASH_METHODS, PaymentMethod
from repuestos.domain.users import User, require_owner
from repuestos.services.audit_service import audit

NO_OPEN_SESSION = "La caja está cerrada. Ábrala en Caja para poder vender."


def _amount(value: Decimal, label: str) -> Decimal:
    if value < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    if value != hu(value, 2):
        raise ValueError(f"{label} admite como máximo 2 decimales.")
    return value


def current_session(conn: sqlite3.Connection) -> CashSession | None:
    return repo.get_open(conn)


def require_open_session(conn: sqlite3.Connection) -> CashSession:
    """Para usar dentro de la transacción de una venta o abono (invariante 6)."""
    session = repo.get_open(conn)
    if session is None:
        raise LookupError(NO_OPEN_SESSION)
    return session


def open_session(conn: sqlite3.Connection, user: User, opening_usd: Decimal, opening_ves: Decimal) -> CashSession:
    """RF-60: apertura con efectivo inicial en USD y en Bs."""
    _amount(opening_usd, "El efectivo inicial en USD")
    _amount(opening_ves, "El efectivo inicial en Bs")
    with transaction(conn):
        if repo.get_open(conn) is not None:
            raise ValueError("Ya hay una caja abierta.")
        session_id = repo.insert(conn, user.id, opening_usd, opening_ves)
        audit(conn, user.id, "CASH_OPEN", "cash_session", session_id, {"usd": opening_usd, "bs": opening_ves})
    session = repo.get(conn, session_id)
    assert session is not None
    return session


def add_movement(
    conn: sqlite3.Connection, user: User, direction: str, currency: str, amount: Decimal, reason: str
) -> int:
    """RF-61: entrada o salida de efectivo, con motivo, por cualquier usuario."""
    if direction not in ("IN", "OUT"):
        raise ValueError("Movimiento de caja inválido.")
    if currency not in ("USD", "VES"):
        raise ValueError("Moneda inválida.")
    _amount(amount, "El monto")
    if amount == 0:
        raise ValueError("El monto debe ser mayor que cero.")
    reason = " ".join(reason.split())
    if not reason:
        raise ValueError("Escriba el motivo.")
    with transaction(conn):
        session = require_open_session(conn)
        movement_id = repo.insert_movement(conn, session.id, direction, currency, amount, reason, user.id)
        audit(
            conn,
            user.id,
            "CASH_IN" if direction == "IN" else "CASH_OUT",
            "cash_session",
            session.id,
            {"moneda": currency, "monto": amount, "motivo": reason},
        )
    return movement_id


@dataclass(frozen=True, slots=True)
class NonCashTotal:
    method: PaymentMethod
    total: Decimal  # en la moneda de la forma de pago
    count: int


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Resumen completo de una sesión. Contiene lo esperado: solo para la dueña."""

    session: CashSession
    expected_usd: Decimal | None  # None en la vista del vendedor (cierre ciego)
    expected_ves: Decimal | None
    cash_usd_payments: Decimal  # Σ CASH_USD (vuelto incluido)
    cash_ves_payments: Decimal
    in_usd: Decimal
    out_usd: Decimal
    in_ves: Decimal
    out_ves: Decimal
    non_cash: tuple[NonCashTotal, ...]
    sales_count: int
    voided_count: int
    sales_total_ves: Decimal
    movements: tuple[CashMovement, ...]

    @property
    def difference_usd(self) -> Decimal | None:
        c, e = self.session.counted_usd, self.expected_usd
        return cash_difference(c, e) if c is not None and e is not None else None

    @property
    def difference_ves(self) -> Decimal | None:
        c, e = self.session.counted_ves, self.expected_ves
        return cash_difference(c, e) if c is not None and e is not None else None


def _summary(conn: sqlite3.Connection, session: CashSession) -> SessionSummary:
    sid = session.id
    usd, _ = repo.sum_payments(conn, sid, PaymentMethod.CASH_USD.value)
    ves, _ = repo.sum_payments(conn, sid, PaymentMethod.CASH_VES.value)
    in_usd, out_usd = repo.sum_movements(conn, sid, "IN", "USD"), repo.sum_movements(conn, sid, "OUT", "USD")
    in_ves, out_ves = repo.sum_movements(conn, sid, "IN", "VES"), repo.sum_movements(conn, sid, "OUT", "VES")
    non_cash = tuple(NonCashTotal(m, *repo.sum_payments(conn, sid, m.value)) for m in NON_CASH_METHODS)
    sales_count, voided_count, sales_total = repo.sales_counts(conn, sid)
    # Si la sesión ya cerró, se usa lo esperado que quedó guardado al cerrar.
    expected_usd = session.expected_usd
    expected_ves = session.expected_ves
    if expected_usd is None or expected_ves is None:
        expected_usd = expected_cash(session.opening_usd, [usd], [in_usd], [out_usd])
        expected_ves = expected_cash(session.opening_ves, [ves], [in_ves], [out_ves])
    return SessionSummary(
        session=session,
        expected_usd=expected_usd,
        expected_ves=expected_ves,
        cash_usd_payments=usd,
        cash_ves_payments=ves,
        in_usd=in_usd,
        out_usd=out_usd,
        in_ves=in_ves,
        out_ves=out_ves,
        non_cash=non_cash,
        sales_count=sales_count,
        voided_count=voided_count,
        sales_total_ves=sales_total,
        movements=tuple(repo.movements(conn, sid)),
    )


def session_summary(conn: sqlite3.Connection, user: User, session_id: int) -> SessionSummary:
    """Lo esperado y la diferencia: solo la dueña (RF-62, RF-63)."""
    require_owner(user, "ver lo esperado en caja")
    session = repo.get(conn, session_id)
    if session is None:
        raise LookupError("La sesión de caja no existe.")
    return _summary(conn, session)


def blind_summary(conn: sqlite3.Connection, session_id: int) -> SessionSummary:
    """Resumen sin lo esperado ni la diferencia: lo que puede ver o imprimir el vendedor."""
    session = repo.get(conn, session_id)
    if session is None:
        raise LookupError("La sesión de caja no existe.")
    hidden = replace(session, expected_usd=None, expected_ves=None)
    return replace(_summary(conn, session), session=hidden, expected_usd=None, expected_ves=None)


@dataclass(frozen=True, slots=True)
class CloseResult:
    session_id: int
    counted_usd: Decimal
    counted_ves: Decimal


def close_session(
    conn: sqlite3.Connection, user: User, counted_usd: Decimal, counted_ves: Decimal, notes: str = ""
) -> CloseResult:
    """RF-62: cierre ciego. Quien cierra escribe lo contado; lo esperado se calcula y guarda en la misma transacción.

    El resultado no trae lo esperado: la dueña lo consulta con ``session_summary``.
    """
    _amount(counted_usd, "Lo contado en USD")
    _amount(counted_ves, "Lo contado en Bs")
    with transaction(conn):
        session = require_open_session(conn)
        s = _summary(conn, session)
        assert s.expected_usd is not None and s.expected_ves is not None
        repo.close(
            conn, session.id, user.id, s.expected_usd, s.expected_ves, counted_usd, counted_ves, " ".join(notes.split())
        )
        audit(
            conn,
            user.id,
            "CASH_CLOSE",
            "cash_session",
            session.id,
            {
                "esperado_usd": s.expected_usd,
                "esperado_bs": s.expected_ves,
                "contado_usd": counted_usd,
                "contado_bs": counted_ves,
                "diferencia_usd": cash_difference(counted_usd, s.expected_usd),
                "diferencia_bs": cash_difference(counted_ves, s.expected_ves),
            },
        )
    return CloseResult(session.id, counted_usd, counted_ves)


def history(conn: sqlite3.Connection, user: User) -> list[CashSession]:
    """RF-63: historial de cierres con diferencias (dueña)."""
    require_owner(user, "ver el historial de caja")
    return repo.history(conn)
