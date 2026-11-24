"""Adapters de instalador disponíveis."""

from __future__ import annotations

from .base import Installer
from .calamares import CalamaresInstaller

INSTALLERS: dict[str, type[Installer]] = {
    "calamares": CalamaresInstaller,
}

__all__ = ["INSTALLERS", "CalamaresInstaller", "Installer"]
