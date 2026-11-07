"""Genera src/repuestos/ui/repuestos.ico (16 a 256 px) dibujado con Qt. Uso: python installer/make_icon.py"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath

SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> bytes:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    m = size * 0.04
    path.addRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), size * 0.2, size * 0.2)
    p.fillPath(path, QColor("#0d47a1"))
    font = QFont("Segoe UI", 1, QFont.Weight.Bold)
    font.setPixelSize(int(size * 0.62))
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(0, -size * 0.02, size, size), Qt.AlignmentFlag.AlignCenter, "R")
    if size >= 32:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffb300"))
        r = size * 0.11
        p.drawEllipse(QRectF(size * 0.72, size * 0.70, r, r))
    p.end()
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data.data())


def write_ico(path: Path) -> None:
    images = [(s, draw(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    path.write_bytes(header + entries + blobs)


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    out = Path(__file__).resolve().parents[1] / "src" / "repuestos" / "ui" / "repuestos.ico"
    write_ico(out)
    print(f"Icono escrito en {out}")
