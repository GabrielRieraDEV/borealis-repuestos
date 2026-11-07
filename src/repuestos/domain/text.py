"""Normalización de texto para la búsqueda (RF-12): minúsculas, sin acentos, solo letras y números."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", without_marks).strip()


def build_search_text(parts: Iterable[str | None]) -> str:
    return " ".join(n for n in (normalize(p) for p in parts if p) if n)


def search_words(query: str) -> list[str]:
    """Palabras de la búsqueda, normalizadas y sin repetir (en orden)."""
    return list(dict.fromkeys(normalize(query).split()))
