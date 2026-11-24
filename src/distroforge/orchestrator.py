"""Orquestrador: liga perfil → catálogo → instalador → builder.

É o único lugar que conhece as duas dimensões ao mesmo tempo. A GUI e a CLI
conversam só com ele.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .builders import BUILDERS, BuildError, BuildResult
from .catalog import Catalog, CatalogError, Resolution
from .container import remove_tree
from .installers import INSTALLERS
from .profile import Profile


@dataclass(slots=True)
class Plan:
    """O que será feito, sem tocar em disco."""

    profile: Profile
    resolution: Resolution
    builder: str
    installer: str
    warnings: list[str] = field(default_factory=list)

    @property
    def distribution(self) -> str:
        return self.profile.variant or self.resolution.base.codename


@dataclass(slots=True)
class Generated:
    workdir: Path
    overlay: Path
    files: list[Path]
    plan: Plan


class Orchestrator:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    # --------------------------------------------------------------- planejar

    def plan(self, profile: Profile) -> Plan:
        resolution = self.catalog.resolve(profile)
        base = resolution.base

        builder_name = (base.builder or "live-build").lower()
        installer_name = (base.installer or "calamares").lower()

        if builder_name not in BUILDERS or installer_name not in INSTALLERS:
            missing = []
            if builder_name not in BUILDERS:
                missing.append(f"builder '{builder_name}'")
            if installer_name not in INSTALLERS:
                missing.append(f"instalador '{installer_name}'")
            raise CatalogError(
                f"{base.label}: {' e '.join(missing)} ainda não implementado(s). "
                f"Builders: {', '.join(sorted(BUILDERS))}. "
                f"Instaladores: {', '.join(sorted(INSTALLERS))}."
            )

        return Plan(
            profile=profile,
            resolution=resolution,
            builder=builder_name,
            installer=installer_name,
            warnings=self._warnings(profile, resolution),
        )

    def _warnings(self, profile: Profile, resolution: Resolution) -> list[str]:
        warnings: list[str] = []
        base = resolution.base

        if not base.is_stable:
            warnings.append(f"'{base.label}' ainda não está estável no catálogo")
        if profile.install_mode == "offline":
            warnings.append(
                "install_mode=offline ainda não implementado; o build gerado é netinstall"
            )
        if profile.arch != "amd64":
            warnings.append(f"arquitetura '{profile.arch}' não foi validada (só amd64)")
        if base.id == "ubuntu":
            warnings.append(
                "build de Ubuntu a partir de container Debian ainda não validado no PoC"
            )
        if resolution.desktop.kind == "wm":
            warnings.append(
                f"'{resolution.desktop.label}' é window manager; "
                "a sessão live ainda sobe openbox apenas para o instalador"
            )

        external = [app.label for app in resolution.apps if app.external]
        if external:
            warnings.append(
                "apps que exigem repositório de terceiros: " + ", ".join(external)
            )
        if not resolution.apps:
            warnings.append("nenhum app selecionado além do desktop")

        return warnings

    # --------------------------------------------------------------- gerar

    def generate(
        self,
        profile: Profile,
        out_dir: str | Path,
        *,
        force: bool = False,
    ) -> Generated:
        plan = self.plan(profile)
        workdir = Path(out_dir) / profile.hostname

        if workdir.exists():
            if not force:
                raise FileExistsError(
                    f"{workdir} já existe; use --force para substituir"
                )
            remove_tree(workdir)
        workdir.mkdir(parents=True)

        profile.save(workdir / "profile.yaml")
        files: list[Path] = [workdir / "profile.yaml"]

        overlay = workdir / "overlay"
        installer = INSTALLERS[plan.installer]()
        files.extend(
            installer.generate(profile, plan.resolution, self.catalog, overlay)
        )

        builder = BUILDERS[plan.builder]()
        files.extend(
            builder.prepare(profile, plan.resolution, self.catalog, workdir, overlay)
        )

        return Generated(workdir=workdir, overlay=overlay, files=files, plan=plan)

    # --------------------------------------------------------------- buildar

    def build(
        self,
        profile: Profile,
        out_dir: str | Path,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> BuildResult:
        generated = self.generate(profile, out_dir, force=force)
        builder = BUILDERS[generated.plan.builder]()

        result = builder.build(profile, generated.workdir, dry_run=dry_run)
        if dry_run:
            return result

        if result.returncode != 0:
            raise BuildError(
                f"build falhou com código {result.returncode}; log em {result.log}"
            )
        if result.iso is None or not result.iso.is_file():
            raise BuildError(
                f"o build terminou sem gerar ISO; veja o log em {result.log}"
            )

        destination = Path(out_dir) / profile.iso_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(result.iso), destination)
        result.iso = destination
        return result
