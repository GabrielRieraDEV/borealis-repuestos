"""Descarga de la tasa oficial USD del BCV (RF-20, RN-01).

Cómo está la página (confirmado con el HTML real del 07/11/2026, guardado en tests/fixtures/bcv.html):

    <div id="dolar" ...> ... <strong class="strong-tb">897,53830000</strong> ... </div>
    ...
    Fecha Valor: <span property="dc:date" datatype="xsd:dateTime" content="2026-11-09T00:00:00-04:00" ...>

- El valor del USD es el texto del primer ``<strong>`` dentro del elemento con ``id="dolar"``. Formato venezolano
  (coma decimal) con 8 decimales; se redondea HU a 6, la escala de ``rate_e6``.
- La fecha valor es el atributo ``content`` del primer ``<span property="dc:date">`` que aparece después del bloque
  del dólar. El BCV publica por adelantado (el viernes ya muestra la del lunes): por eso se guarda la fecha valor.

Si el BCV cambia la página y el parser deja de funcionar:
1. Guarde el HTML nuevo en ``tests/fixtures/bcv.html`` (``curl -o tests/fixtures/bcv.html https://www.bcv.org.ve/``).
2. Busque el bloque del USD y la fecha valor y ajuste ``_BcvParser`` (el id del bloque y la etiqueta del valor).
3. Actualice el valor esperado en ``tests/test_bcv.py`` y corra ``pytest tests/test_bcv.py``.
Mientras tanto, la dueña carga la tasa a mano (Tasa BCV > Cargar tasa manual).

Nunca se desactiva la verificación TLS (RN-01). Se usa el almacén de certificados de Windows (``truststore``)
cuando está disponible, porque el BCV a veces sirve una cadena que solo Windows sabe completar.
"""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

import httpx

from repuestos.domain.money import hu

log = logging.getLogger(__name__)

BCV_URL = "https://www.bcv.org.ve/"
TIMEOUT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BorealisRepuestos/1.0"


class BcvError(Exception):
    """No se pudo obtener la tasa del BCV (red, certificado o página cambiada)."""


@dataclass(frozen=True, slots=True)
class BcvRate:
    rate: Decimal
    valid_date: date


class _BcvParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0  # profundidad dentro del bloque id="dolar"; 0 = fuera
        self._in_strong = False
        self.seen_dolar = False
        self.rate_text: str | None = None
        self.valid_date_text: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if self._depth:
            self._depth += 1
            if tag == "strong" and self.rate_text is None:
                self._in_strong = True
        elif a.get("id") == "dolar" and not self.seen_dolar:
            self.seen_dolar = True
            self._depth = 1
        if (
            self.seen_dolar
            and self.valid_date_text is None
            and tag == "span"
            and a.get("property") == "dc:date"
            and a.get("content")
        ):
            self.valid_date_text = a["content"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "strong":
            self._in_strong = False
        if self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_strong and self.rate_text is None and data.strip():
            self.rate_text = data.strip()


def _parse_ve_number(text: str) -> Decimal:
    normalized = text.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        raise BcvError(f"El valor del USD no es un número: {text!r}") from None
    if not value.is_finite() or value <= 0:
        raise BcvError(f"El valor del USD no es válido: {text!r}")
    return value


def parse_bcv_html(html: str) -> BcvRate:
    parser = _BcvParser()
    parser.feed(html)
    parser.close()
    if not parser.seen_dolar:
        raise BcvError("No se encontró el bloque id='dolar' en la página del BCV.")
    if parser.rate_text is None:
        raise BcvError("No se encontró el valor del USD en la página del BCV.")
    if parser.valid_date_text is None:
        raise BcvError("No se encontró la fecha valor en la página del BCV.")
    try:
        valid_date = date.fromisoformat(parser.valid_date_text[:10])
    except ValueError:
        raise BcvError(f"Fecha valor no reconocida: {parser.valid_date_text!r}") from None
    return BcvRate(rate=hu(_parse_ve_number(parser.rate_text), 6), valid_date=valid_date)


def _ssl_context() -> ssl.SSLContext | bool:
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:  # pragma: no cover - truststore es dependencia del proyecto
        return True


def fetch_bcv_rate(url: str = BCV_URL, timeout: int = TIMEOUT_SECONDS) -> BcvRate:
    """Descarga y lee la tasa. Lanza BcvError ante cualquier falla (el llamador sigue sin interrumpir nada)."""
    try:
        with httpx.Client(
            timeout=timeout, verify=_ssl_context(), headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("No se pudo descargar la tasa del BCV: %s", exc)
        raise BcvError(str(exc)) from exc
    return parse_bcv_html(response.text)
