"""Repositorio de usuarios."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from repuestos.domain.users import Role, User


@dataclass(frozen=True, slots=True)
class UserAuthRow:
    user: User
    password_hash: str
    failed_attempts: int
    locked_until: str | None


def _to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        full_name=row["full_name"],
        role=Role(row["role"]),
        active=bool(row["active"]),
    )


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _to_user(row) if row else None


def get_auth(conn: sqlite3.Connection, username: str) -> UserAuthRow | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    return UserAuthRow(_to_user(row), row["password_hash"], row["failed_attempts"], row["locked_until"])


def insert(conn: sqlite3.Connection, username: str, full_name: str, role: Role, password_hash: str) -> int:
    cur = conn.execute(
        "INSERT INTO users (username, full_name, role, password_hash) VALUES (?, ?, ?, ?)",
        (username, full_name, role.value, password_hash),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def set_login_failure(conn: sqlite3.Connection, user_id: int, failed_attempts: int, locked_until: str | None) -> None:
    conn.execute(
        "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
        (failed_attempts, locked_until, user_id),
    )


def reset_login_state(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user_id,))


def list_all(conn: sqlite3.Connection) -> list[User]:
    return [_to_user(r) for r in conn.execute("SELECT * FROM users ORDER BY role, full_name COLLATE NOCASE")]


def active_owner_hashes(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    rows = conn.execute("SELECT id, password_hash FROM users WHERE role = 'owner' AND active = 1 ORDER BY id")
    return [(r["id"], r["password_hash"]) for r in rows]


def set_active(conn: sqlite3.Connection, user_id: int, active: bool) -> None:
    conn.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))


def set_password_hash(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?",
        (password_hash, user_id),
    )
