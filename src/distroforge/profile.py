"""Perfil neutro do DistroForge.

É o único contrato entre a interface, a CLI e os backends. O formato é o mesmo
que o site exporta em ``profile.yaml``, então um perfil gerado no navegador roda
na CLI sem conversão.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

BASES = ("debian", "ubuntu", "arch", "fedora", "opensuse")
ARCHES = ("amd64", "arm64")
INSTALL_MODES = ("netinstall", "offline")
FALLBACKS = ("none", "minimal")

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class ProfileError(ValueError):
    """Perfil ausente, malformado ou incoerente."""


def slugify(text: str) -> str:
    """Converte um nome livre em hostname/identificador seguro."""
    normalized = unicodedata.normalize("NFD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:63].strip("-") or "minhadistro"


@dataclass(slots=True)
class Profile:
    """Descrição declarativa de uma distro."""

    name: str = "MinhaDistro"
    version: str = "1.0"
    hostname: str = ""
    base: str = "debian"
    variant: str = ""
    arch: str = "amd64"
    install_mode: str = "netinstall"
    desktop: str = "kde"
    apps: list[str] = field(default_factory=list)
    color: str = "#3b82f6"
    iso_name: str = ""
    offline_fallback: str = "minimal"

    # ------------------------------------------------------------------ init

    def __post_init__(self) -> None:
        self.name = str(self.name).strip() or "MinhaDistro"
        self.version = str(self.version).strip() or "1.0"
        self.hostname = slugify(self.hostname or self.name)
        self.base = str(self.base).strip().lower()
        self.variant = str(self.variant).strip()
        self.arch = str(self.arch).strip().lower()
        self.install_mode = str(self.install_mode).strip().lower()
        self.desktop = str(self.desktop).strip().lower()
        self.color = str(self.color).strip()
        self.offline_fallback = str(self.offline_fallback).strip().lower()

        self.apps = _dedupe([str(app).strip() for app in self.apps if str(app).strip()])

        if not self.iso_name:
            self.iso_name = f"{self.hostname}-{self.version}-{self.arch}.iso"

        self.validate()

    def validate(self) -> None:
        problems: list[str] = []

        if self.base not in BASES:
            problems.append(f"base '{self.base}' inválida (use: {', '.join(BASES)})")
        if self.arch not in ARCHES:
            problems.append(f"arch '{self.arch}' inválida (use: {', '.join(ARCHES)})")
        if self.install_mode not in INSTALL_MODES:
            problems.append(
                f"install_mode '{self.install_mode}' inválido (use: {', '.join(INSTALL_MODES)})"
            )
        if self.offline_fallback not in FALLBACKS:
            problems.append(
                f"offline_fallback '{self.offline_fallback}' inválido "
                f"(use: {', '.join(FALLBACKS)})"
            )
        if not _COLOR_RE.match(self.color):
            problems.append(f"cor de branding '{self.color}' inválida (esperado #rrggbb)")
        if not _HOSTNAME_RE.match(self.hostname):
            problems.append(f"hostname '{self.hostname}' inválido")
        if not self.desktop:
            problems.append("desktop não pode ser vazio")
        if not self.iso_name.endswith(".iso"):
            self.iso_name = f"{self.iso_name}.iso"

        if problems:
            raise ProfileError("; ".join(problems))

    # --------------------------------------------------------------- load/save

    @classmethod
    def from_dict(cls, data: Any) -> Profile:
        if not isinstance(data, dict):
            raise ProfileError("o perfil precisa ser um mapa YAML")

        meta = data.get("meta") or {}
        branding = data.get("branding") or {}
        if not isinstance(meta, dict) or not isinstance(branding, dict):
            raise ProfileError("'meta' e 'branding' precisam ser mapas")

        apps = data.get("apps_default", data.get("apps", []))
        if apps is None:
            apps = []
        if not isinstance(apps, list):
            raise ProfileError("'apps_default' precisa ser uma lista")

        return cls(
            name=meta.get("name", data.get("name", "MinhaDistro")),
            version=meta.get("version", data.get("version", "1.0")),
            hostname=meta.get("hostname", ""),
            base=data.get("base", "debian"),
            variant=data.get("variant", ""),
            arch=data.get("arch", "amd64"),
            install_mode=data.get("install_mode", "netinstall"),
            desktop=data.get("desktop_default", data.get("desktop", "kde")),
            apps=apps,
            color=branding.get("color", "#3b82f6"),
            iso_name=branding.get("iso_name", ""),
            offline_fallback=data.get("offline_fallback", "minimal"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> Profile:
        file = Path(path)
        if not file.is_file():
            raise ProfileError(f"perfil não encontrado: {file}")
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ProfileError(f"YAML inválido em {file}: {error}") from error
        if data is None:
            raise ProfileError(f"perfil vazio: {file}")
        # Caminho relativo para mensagens de erro melhores
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": {
                "name": self.name,
                "version": self.version,
                "hostname": self.hostname,
            },
            "base": self.base,
            "variant": self.variant,
            "arch": self.arch,
            "install_mode": self.install_mode,
            "desktop_default": self.desktop,
            "apps_default": list(self.apps),
            "branding": {
                "color": self.color,
                "iso_name": self.iso_name,
            },
            "offline_fallback": self.offline_fallback,
        }

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    def save(self, path: str | Path) -> Path:
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(self.to_yaml(), encoding="utf-8")
        return file

    # ------------------------------------------------------------------ props

    @property
    def product_name(self) -> str:
        return f"{self.name} {self.version}"

    @property
    def title(self) -> str:
        return f"{self.name} — {self.version}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
