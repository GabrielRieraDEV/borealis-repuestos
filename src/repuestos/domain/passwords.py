"""Hash de contraseñas con scrypt de la biblioteca estándar (RF-01).

Formato guardado en ``users.password_hash``: ``scrypt$n$r$p$salt_b64$hash_b64``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N = 2**14
R = 8
P = 1
DKLEN = 32
MIN_LENGTH = 6


def validate_new_password(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_LENGTH} caracteres.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return "$".join(
        ["scrypt", str(N), str(R), str(P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# ------------------------------------------------------------------ código de recuperación de la dueña

RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I/L: se copia a mano sin confusiones
RECOVERY_GROUPS = 3
RECOVERY_GROUP_LEN = 4


def generate_recovery_code() -> str:
    """Código de 12 caracteres al azar en grupos de 4 (≈ 60 bits): K7QM-3XR9-PW2H."""
    chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_GROUPS * RECOVERY_GROUP_LEN))
    return "-".join(chars[i : i + RECOVERY_GROUP_LEN] for i in range(0, len(chars), RECOVERY_GROUP_LEN))


def normalize_recovery_code(text: str) -> str:
    """Acepta minúsculas, espacios y guiones: «k7qm 3xr9 pw2h» = «K7QM-3XR9-PW2H»."""
    return "".join(c for c in text.upper() if c.isalnum())
