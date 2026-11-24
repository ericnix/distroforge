"""Adapter do Calamares.

Gera a árvore ``/etc/calamares`` completa a partir do perfil: sequência de
módulos, ``packagechooser`` (desktop), ``netinstall`` (programas) e branding.
Nada aqui depende de código C++ novo — são só arquivos de configuração dos
módulos que já vêm no pacote ``calamares``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..catalog import Catalog, Resolution
from ..profile import Profile
from .base import Installer

# Onde o squashfs do live está montado, por família de base.
UNPACK_SOURCES = {
    "debian": "/run/live/medium/live/filesystem.squashfs",
    "ubuntu": "/run/live/medium/live/filesystem.squashfs",
    "arch": "/run/archiso/bootmnt/arch/x86_64/airootfs.sfs",
}

SHOW_SEQUENCE = [
    "welcome",
    "locale",
    "keyboard",
    "partition",
    "users",
    "packagechooser",
    "netinstall",
    "summary",
]

EXEC_SEQUENCE = [
    "partition",
    "mount",
    "unpackfs",
    "machineid",
    "fstab",
    "locale",
    "keyboard",
    "localecfg",
    "users",
    "displaymanager",
    "networkcfg",
    "hwclock",
    "services-systemd",
    "packagechooser",
    "netinstall",
    "packages",
    "bootloader",
    "umount",
]

DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=Instalar {product}
Comment=Instalar {product} no computador
Exec=sudo -E calamares
Icon=calamares
Terminal=false
Categories=System;
"""


class CalamaresInstaller(Installer):
    name = "calamares"

    def generate(
        self,
        profile: Profile,
        resolution: Resolution,
        catalog: Catalog,
        overlay: Path,
    ) -> list[Path]:
        calamares = overlay / "etc" / "calamares"
        modules = calamares / "modules"
        branding = calamares / "branding" / profile.hostname

        base_id = resolution.base.id
        unpack_source = UNPACK_SOURCES.get(base_id)
        if unpack_source is None:
            unpack_source = "/run/live/medium/live/filesystem.squashfs"

        written: list[Path] = []
        written.append(self._write_yaml(calamares / "settings.conf", self._settings(profile)))
        written.append(
            self._write_yaml(
                modules / "unpackfs.conf",
                {
                    "unpack": [
                        {
                            "source": unpack_source,
                            "sourcefs": "squashfs",
                            "destination": "",
                        }
                    ]
                },
            )
        )
        written.append(
            self._write_yaml(
                modules / "packagechooser.conf",
                self._packagechooser(profile, resolution, catalog),
            )
        )

        groups = self._netinstall_groups(profile, resolution, catalog)
        written.append(self._write_yaml(calamares / "netinstall.yaml", groups))
        written.append(
            self._write_yaml(
                modules / "netinstall.conf",
                {"groupsUrl": "/etc/calamares/netinstall.yaml"},
            )
        )
        written.append(self._write_yaml(branding / "branding.desc", self._branding(profile)))
        written.append(
            self._write(
                overlay / "usr" / "share" / "applications" / "install-distro.desktop",
                DESKTOP_TEMPLATE.format(product=profile.product_name),
            )
        )
        written.append(
            self._write(
                overlay / "etc" / "skel" / "Desktop" / "install-distro.desktop",
                DESKTOP_TEMPLATE.format(product=profile.product_name),
            )
        )
        return written

    # ------------------------------------------------------------- seções

    @staticmethod
    def _settings(profile: Profile) -> dict[str, Any]:
        return {
            "modules-search": ["local", "/usr/lib/calamares/modules"],
            "instances": [],
            "sequence": [
                {"show": list(SHOW_SEQUENCE)},
                {"exec": list(EXEC_SEQUENCE)},
            ],
            "branding": profile.hostname,
            "prompt-install": False,
            "dont-chroot": False,
        }

    def _packagechooser(
        self, profile: Profile, resolution: Resolution, catalog: Catalog
    ) -> dict[str, Any]:
        labels = []
        for item in catalog.graphical_for(resolution.base.id):
            size = item.size_for(resolution.base.id)
            description = item.summary
            if size:
                description = f"{description} ({_fmt_mb(size)})"
            labels.append(
                {
                    "name": item.label,
                    "description": description,
                    "packages": item.packages(resolution.base.id),
                }
            )
        return {"id": "desktop", "labels": labels}

    def _netinstall_groups(
        self, profile: Profile, resolution: Resolution, catalog: Catalog
    ) -> list[dict[str, Any]]:
        chosen = set(profile.apps)
        groups: list[dict[str, Any]] = []

        for category in catalog.categories:
            category_id = str(category.get("id", ""))
            apps = catalog.apps_in(resolution.base.id, category_id)
            if not apps:
                continue

            subcategories = []
            for app in apps:
                description = _fmt_mb(app.size_for(resolution.base.id)) if app.size_for(resolution.base.id) else ""
                if app.external:
                    description = f"{description} · repositório de terceiros".strip(" ·")
                subcategories.append(
                    {
                        "name": app.label,
                        "description": description,
                        "packages": app.packages(resolution.base.id),
                        "selected": app.id in chosen,
                    }
                )

            groups.append(
                {
                    "name": str(category.get("label", category_id)),
                    "description": "",
                    "expanded": any(app.id in chosen for app in apps),
                    "subcategories": subcategories,
                }
            )

        return groups

    @staticmethod
    def _branding(profile: Profile) -> dict[str, Any]:
        return {
            "componentName": profile.hostname,
            "strings": {
                "productName": profile.product_name,
                "shortProductName": profile.name,
                "version": profile.version,
                "shortVersion": profile.version,
                "versionedName": profile.product_name,
                "bootloaderEntryName": profile.name,
                "productUrl": "https://distroforge-site.pages.dev",
                "supportUrl": "https://github.com/ericnix/distroforge/issues",
            },
            "style": {
                "sidebarBackground": "#06070b",
                "sidebarText": "#e9ecf5",
                "sidebarTextSelect": "#7aa7ff",
                "sidebarTextHighlight": "#4f8ef7",
            },
            "windowExpandedSize": "1024x700",
        }

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _write_yaml(path: Path, data: Any) -> Path:
        content = yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000,
        )
        return Installer._write(path, "# gerado pelo DistroForge — não edite à mão\n" + content)


def _fmt_mb(mb: int) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB".replace(".", ",")
    return f"{mb} MB"
