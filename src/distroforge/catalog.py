"""Catálogo: a capacidade ("KDE", "Firefox") traduzida para o pacote certo em
cada base.

Lê ``catalog/{bases,desktops,wms,apps}.yaml`` — os mesmos arquivos que alimentam
o site. Nada aqui é específico de uma distro: quem sabe montar a ISO é o builder.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# Estimativas usadas no site: base mínima instalada + expansão dos pacotes.
BASE_MIN_MB = {
    "debian": 1300,
    "ubuntu": 1400,
    "arch": 1000,
    "fedora": 1350,
    "opensuse": 1400,
}
DISK_EXPANSION = 1.9
ISO_OVERHEAD_MB = 30


class CatalogError(ValueError):
    """Catálogo ausente, inválido ou combinação impossível."""


@dataclass(slots=True)
class Base:
    id: str
    label: str
    release: str
    status: str
    iso_size: int
    pkg_manager: str
    builder: str
    installer: str
    accent: str
    summary: str
    codename: str = ""

    @property
    def is_stable(self) -> bool:
        return self.status == "stable"

    @property
    def build_codename(self) -> str:
        """Codinome usado por ferramentas de build."""
        if self.codename:
            return self.codename
        if "(" in self.release and ")" in self.release:
            return self.release.split("(", 1)[1].split(")", 1)[0].strip()
        return self.release.strip()


@dataclass(slots=True)
class Item:
    id: str
    label: str
    kind: str  # desktop | wm | app
    summary: str = ""
    size: dict[str, int] = field(default_factory=dict)
    pkgs: dict[str, list[str]] = field(default_factory=dict)
    category: str | None = None
    default: bool = False
    external: bool = False
    note: str = ""

    def available(self, base: str) -> bool:
        return bool(self.pkgs.get(base))

    def packages(self, base: str) -> list[str]:
        return list(self.pkgs.get(base, []))

    def size_for(self, base: str) -> int:
        return int(self.size.get(base, 0))


@dataclass(slots=True)
class Resolution:
    """Perfil + catálogo resolvidos: pacotes, tamanhos e o que foi escolhido."""

    base: Base
    desktop: Item
    apps: list[Item]
    packages: list[str]
    download_mb: int
    iso_mb: int
    disk_mb: int

    @property
    def app_ids(self) -> list[str]:
        return [app.id for app in self.apps]


class Catalog:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        bases_doc = self._load("bases.yaml")
        desktops_doc = self._load("desktops.yaml")
        wms_doc = self._load("wms.yaml")
        apps_doc = self._load("apps.yaml")

        self._bases = [self._base(entry) for entry in _require_list(bases_doc, "bases", "bases.yaml")]
        self._desktops = [
            self._item(entry, "desktop") for entry in _require_list(desktops_doc, "desktops", "desktops.yaml")
        ]
        self._wms = [self._item(entry, "wm") for entry in _require_list(wms_doc, "wms", "wms.yaml")]
        self._apps = [self._item(entry, "app") for entry in _require_list(apps_doc, "apps", "apps.yaml")]
        self._categories = list(apps_doc.get("categories") or [])

        self._bases_by_id = {base.id: base for base in self._bases}
        self._items_by_id = {
            item.id: item for item in (*self._desktops, *self._wms, *self._apps)
        }
        self._validate()

    # ------------------------------------------------------------------ load

    @classmethod
    def locate(cls, start: str | Path | None = None) -> Catalog:
        """Encontra o catálogo subindo diretórios a partir de ``start``."""
        env = os.environ.get("DISTROFORGE_CATALOG")
        if env:
            root = Path(env).expanduser().resolve()
            if not (root / "bases.yaml").is_file():
                raise CatalogError(f"DISTROFORGE_CATALOG não contém bases.yaml: {root}")
            return cls(root)

        candidates: list[Path] = []
        if start:
            candidates.append(Path(start).expanduser().resolve())
        candidates.append(Path.cwd())
        candidates.append(Path(__file__).resolve().parent)

        packaged = Path(__file__).resolve().parent / "catalog_data"
        if (packaged / "bases.yaml").is_file():
            return cls(packaged)

        for candidate in candidates:
            for directory in (candidate, *candidate.parents):
                root = directory / "catalog"
                if (root / "bases.yaml").is_file():
                    return cls(root)

        raise CatalogError(
            "catálogo não encontrado (procurei por catalog/bases.yaml); "
            "rode dentro do repositório ou defina DISTROFORGE_CATALOG"
        )

    def _load(self, name: str) -> dict[str, Any]:
        path = self.root / name
        if not path.is_file():
            raise CatalogError(f"arquivo do catálogo ausente: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise CatalogError(f"YAML inválido em {path}: {error}") from error
        if not isinstance(data, dict):
            raise CatalogError(f"{path} deveria conter um mapa YAML")
        return data

    @staticmethod
    def _base(entry: dict[str, Any]) -> Base:
        try:
            return Base(
                id=str(entry["id"]),
                label=str(entry["label"]),
                release=str(entry.get("release", "")),
                status=str(entry.get("status", "stable")),
                codename=str(entry.get("codename", "")),
                iso_size=int(entry.get("iso_size", 0)),
                pkg_manager=str(entry.get("pkg_manager", "")),
                builder=str(entry.get("builder", "")),
                installer=str(entry.get("installer", "")),
                accent=str(entry.get("accent", "#3b82f6")),
                summary=str(entry.get("summary", "")),
            )
        except KeyError as error:
            raise CatalogError(f"base sem campo obrigatório: {error}") from error

    @staticmethod
    def _item(entry: dict[str, Any], kind: str) -> Item:
        try:
            item_id = str(entry["id"])
        except KeyError as error:
            raise CatalogError(f"{kind} sem 'id' no catálogo") from error
        pkgs = {
            str(base): [str(pkg) for pkg in (values or [])]
            for base, values in (entry.get("pkgs") or {}).items()
        }
        size = {
            str(base): int(value or 0)
            for base, value in (entry.get("size") or {}).items()
        }
        return Item(
            id=item_id,
            label=str(entry.get("label", item_id)),
            kind=kind,
            summary=str(entry.get("summary", "")),
            size=size,
            pkgs=pkgs,
            category=entry.get("category"),
            default=bool(entry.get("default", False)),
            external=bool(entry.get("external", False)),
            note=str(entry.get("note", "")),
        )

    def _validate(self) -> None:
        problems: list[str] = []

        for item in (*self._desktops, *self._wms, *self._apps):
            for base_id in item.pkgs:
                if base_id not in self._bases_by_id:
                    problems.append(f"{item.kind}/{item.id}: base desconhecida '{base_id}'")
            if not item.pkgs:
                problems.append(f"{item.kind}/{item.id}: sem pacotes para base alguma")

        categories = {str(category.get("id")) for category in self._categories}
        for app in self._apps:
            if app.category and app.category not in categories:
                problems.append(f"app/{app.id}: categoria desconhecida '{app.category}'")

        seen: set[str] = set()
        for item in (*self._desktops, *self._wms, *self._apps):
            if item.id in seen:
                problems.append(f"id duplicado no catálogo: '{item.id}'")
            seen.add(item.id)

        if problems:
            raise CatalogError("catálogo inválido:\n  - " + "\n  - ".join(problems))

    # --------------------------------------------------------------- queries

    @property
    def bases(self) -> list[Base]:
        return list(self._bases)

    @property
    def desktops(self) -> list[Item]:
        return list(self._desktops)

    @property
    def wms(self) -> list[Item]:
        return list(self._wms)

    @property
    def apps(self) -> list[Item]:
        return list(self._apps)

    @property
    def categories(self) -> list[dict[str, Any]]:
        return list(self._categories)

    def base(self, base_id: str) -> Base:
        try:
            return self._bases_by_id[base_id]
        except KeyError:
            raise CatalogError(
                f"base '{base_id}' não existe no catálogo (disponíveis: {', '.join(self._bases_by_id)})"
            ) from None

    def app(self, app_id: str) -> Item | None:
        item = self._items_by_id.get(app_id)
        return item if item and item.kind == "app" else None

    def desktops_for(self, base_id: str) -> list[Item]:
        return [desktop for desktop in self._desktops if desktop.available(base_id)]

    def wms_for(self, base_id: str) -> list[Item]:
        return [wm for wm in self._wms if wm.available(base_id)]

    def graphical_for(self, base_id: str) -> list[Item]:
        return [*self.desktops_for(base_id), *self.wms_for(base_id)]

    def apps_for(self, base_id: str) -> list[Item]:
        return [app for app in self._apps if app.available(base_id)]

    def apps_in(self, base_id: str, category_id: str) -> list[Item]:
        return [
            app
            for app in self.apps_for(base_id)
            if app.category == category_id
        ]

    def default_apps(self, base_id: str) -> list[str]:
        return [app.id for app in self.apps_for(base_id) if app.default]

    # --------------------------------------------------------------- resolve

    def resolve(self, profile) -> Resolution:
        """Traduz o perfil em pacotes e tamanhos, ou explica por que não dá."""
        base = self.base(profile.base)

        graphical = self.graphical_for(base.id)
        desktop = next((item for item in graphical if item.id == profile.desktop), None)
        if desktop is None:
            available = ", ".join(item.id for item in graphical) or "nenhum"
            raise CatalogError(
                f"'{profile.desktop}' não está disponível em {base.label} "
                f"(disponíveis: {available})"
            )

        apps: list[Item] = []
        unknown: list[str] = []
        unavailable: list[str] = []
        for app_id in profile.apps:
            app = self.app(app_id)
            if app is None:
                unknown.append(app_id)
            elif not app.available(base.id):
                unavailable.append(app_id)
            else:
                apps.append(app)

        if unknown:
            raise CatalogError(f"apps desconhecidos: {', '.join(unknown)}")
        if unavailable:
            raise CatalogError(
                f"apps indisponíveis em {base.label}: {', '.join(unavailable)}"
            )

        packages = _dedupe([*desktop.packages(base.id), *(pkg for app in apps for pkg in app.packages(base.id))])
        download = desktop.size_for(base.id) + sum(app.size_for(base.id) for app in apps)
        iso_mb = base.iso_size + ISO_OVERHEAD_MB
        disk_mb = BASE_MIN_MB.get(base.id, 1300) + round(download * DISK_EXPANSION)

        return Resolution(
            base=base,
            desktop=desktop,
            apps=apps,
            packages=packages,
            download_mb=download,
            iso_mb=iso_mb,
            disk_mb=disk_mb,
        )


def _require_list(doc: dict[str, Any], key: str, filename: str) -> list[dict[str, Any]]:
    value = doc.get(key)
    if not isinstance(value, list):
        raise CatalogError(f"{filename}: '{key}' precisa ser uma lista")
    return value


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
