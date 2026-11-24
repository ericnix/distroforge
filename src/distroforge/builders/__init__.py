"""Builders disponíveis, indexados pelo nome que aparece no catálogo."""

from __future__ import annotations

from .archiso import ArchisoBuilder
from .base import Builder, BuildError, BuildResult
from .livebuild import LiveBuildBuilder

BUILDERS: dict[str, type[Builder]] = {
    "live-build": LiveBuildBuilder,
    "archiso": ArchisoBuilder,
}

__all__ = [
    "BUILDERS",
    "ArchisoBuilder",
    "BuildError",
    "BuildResult",
    "Builder",
    "LiveBuildBuilder",
]
