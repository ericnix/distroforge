"""Interface dos adapters de instalador."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..catalog import Catalog, Resolution
from ..profile import Profile


class Installer(ABC):
    """Traduz o perfil neutro na configuração do instalador escolhido.

    O adapter escreve em um diretório de overlay (raiz do rootfs do live); quem
    copia esse overlay para dentro do builder é o orquestrador.
    """

    name: str = "installer"

    @abstractmethod
    def generate(
        self,
        profile: Profile,
        resolution: Resolution,
        catalog: Catalog,
        overlay: Path,
    ) -> list[Path]:
        """Escreve os arquivos de configuração e devolve os caminhos criados."""

    @staticmethod
    def _write(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
