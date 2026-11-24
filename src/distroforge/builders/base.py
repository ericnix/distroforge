"""Interface dos builders de live ISO."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..catalog import Catalog, Resolution
from ..profile import Profile


@dataclass(slots=True)
class BuildResult:
    workdir: Path
    command: list[str] = field(default_factory=list)
    iso: Path | None = None
    log: Path | None = None
    dry_run: bool = False
    returncode: int = 0


class BuildError(RuntimeError):
    """Falha ao montar o live ISO."""


class Builder(ABC):
    """Sabe transformar perfil + overlay em uma ISO inicializável."""

    name: str = "builder"

    @abstractmethod
    def prepare(
        self,
        profile: Profile,
        resolution: Resolution,
        catalog: Catalog,
        workdir: Path,
        overlay: Path,
    ) -> list[Path]:
        """Escreve a árvore de build e devolve os arquivos criados."""

    @abstractmethod
    def build(
        self,
        profile: Profile,
        workdir: Path,
        *,
        dry_run: bool = False,
        on_line=None,
    ) -> BuildResult:
        """Executa o build (normalmente em container) e devolve o resultado."""

    @staticmethod
    def _write(path: Path, content: str, executable: bool = False) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path
