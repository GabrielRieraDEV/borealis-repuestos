"""Usuarios y roles (PRD §2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    SELLER = "seller"


ROLE_LABELS = {Role.OWNER: "Dueña", Role.SELLER: "Vendedor"}


@dataclass(frozen=True, slots=True)
class User:
    id: int
    username: str
    full_name: str
    role: Role
    active: bool

    @property
    def is_owner(self) -> bool:
        return self.role is Role.OWNER


def require_owner(user: User, action: str = "esta acción") -> None:
    """El servicio niega lo que la UI oculta (CLAUDE.md, Interfaz)."""
    if not user.is_owner:
        raise PermissionError(f"Solo la dueña puede hacer {action}.")
