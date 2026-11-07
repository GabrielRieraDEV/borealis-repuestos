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
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)
