"""DistroForge — núcleo do construtor de distros.

Camadas:

- ``profile``      perfil neutro (único contrato entre GUI, CLI e backends)
- ``catalog``      capacidade → pacote por base (lê ``catalog/*.yaml``)
- ``installers``   como apresentar as opções na instalação (Calamares, ...)
- ``builders``     como montar o live ISO (live-build, archiso, ...)
- ``orchestrator`` liga perfil → catálogo → instalador → builder
"""

from __future__ import annotations

__version__ = "0.1.0"

from .catalog import Catalog, CatalogError, Item, Resolution, Base
from .orchestrator import Orchestrator, Plan
from .profile import Profile, ProfileError, slugify

__all__ = [
    "__version__",
    "Base",
    "Catalog",
    "CatalogError",
    "Item",
    "Orchestrator",
    "Plan",
    "Profile",
    "ProfileError",
    "Resolution",
    "slugify",
]
