"""Rótulos seguros para mídia (ISO 9660 é bem restritivo)."""

from __future__ import annotations

import re

# ISO 9660 (ECMA-119) aceita apenas A-Z, 0-9 e _ no rótulo do volume.
_ALLOWED = re.compile(r"[^A-Z0-9_]")


def iso_volume_label(text: str, max_len: int = 32) -> str:
    """Converte texto livre em um rótulo válido para o volume ISO.

    >>> iso_volume_label("Minha Distro 1.0")
    'MINHA_DISTRO_1_0'
    """
    label = _ALLOWED.sub("_", (text or "").upper())
    label = re.sub(r"_{2,}", "_", label).strip("_")
    label = label[:max_len].strip("_")
    return label or "DISTROFORGE"
