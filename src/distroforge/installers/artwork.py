"""Gera imagens de branding sem dependências externas.

Um PNG com gradiente vertical é suficiente para logo, tela de boas-vindas e
miniatura do seletor de desktop. Assim o repositório não carrega binários e o
branding funciona em qualquer build.
"""

from __future__ import annotations

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        value = "3b82f6"
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def gradient_png(
    width: int,
    height: int,
    top: str = "#0b1120",
    bottom: str = "#1b2a4a",
    accent: str | None = None,
    accent_rows: tuple[float, float] = (0.72, 0.85),
) -> bytes:
    """PNG RGB com gradiente vertical e uma barra de destaque opcional."""
    top_rgb = _rgb(top)
    bottom_rgb = _rgb(bottom)
    accent_rgb = _rgb(accent) if accent else None
    start_row = int(height * accent_rows[0])
    end_row = int(height * accent_rows[1])
    margin = max(1, int(width * 0.06))

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filtro: none
        ratio = y / max(height - 1, 1)
        base = tuple(
            round(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * ratio) for i in range(3)
        )
        for x in range(width):
            if (
                accent_rgb
                and start_row <= y <= end_row
                and margin <= x < width - margin
            ):
                raw.extend(accent_rgb)
            else:
                raw.extend(base)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )
