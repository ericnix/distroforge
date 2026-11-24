"""Interface gráfica do DistroForge (PySide6)."""

from __future__ import annotations

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from .app import main as _main

    return _main(argv)
