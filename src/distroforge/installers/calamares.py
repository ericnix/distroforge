"""Adapter do Calamares.

Gera a árvore ``/etc/calamares`` completa a partir do perfil: sequência de
módulos, ``packagechooser`` (desktop), ``netinstall`` (programas) e branding.
Nada aqui depende de código C++ novo — são só arquivos de configuração dos
módulos que já vêm no pacote ``calamares``.
"""

from __future__ import annotations

import base64
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
    "netinstall",
    "packages",
    "bootloader",
    "umount",
]

# Placeholder 160x90 usado como screenshot dos itens do packagechooser.
SCREENSHOT_PNG_B64 = (
    "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"
)

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
        # Calamares procura branding em /usr/share/calamares/branding, não em /etc.
        branding = overlay / "usr" / "share" / "calamares" / "branding" / profile.hostname

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
                {"groupsUrl": "file:///etc/calamares/netinstall.yaml"},
            )
        )
        written.append(self._write_yaml(branding / "branding.desc", self._branding(profile)))
        shot = branding / "screenshot.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(base64.b64decode(SCREENSHOT_PNG_B64))
        written.append(shot)
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
            # Sem modules-search: o Calamares usa o caminho compilado
            # (multiarch, /usr/lib/x86_64-linux-gnu/calamares/modules).
            # Declarar a lista substitui esse caminho e quebra o carregamento.
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
        items = []
        for item in catalog.graphical_for(resolution.base.id):
            size = item.size_for(resolution.base.id)
            description = item.summary
            if size:
                description = f"{description} ({_fmt_mb(size)})"
            items.append(
                {
                    "id": item.id,
                    "name": item.label,
                    "description": description,
                    "packages": item.packages(resolution.base.id),
                    "screenshot": "screenshot.png",
                }
            )
        # mode/method são obrigatórios no Calamares 3.3; com method=packages
        # a escolha é entregue ao módulo packages do exec.
        return {
            "mode": "required",
            "method": "packages",
            "labels": {"step": "Desktop"},
            "items": items,
        }

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
                    "description": str(category.get("label", category_id)),
                    "selected": False,
                    "expanded": any(app.id in chosen for app in apps),
                    "subgroups": subcategories,
                }
            )

        return groups

    @staticmethod
    def _branding(profile: Profile) -> dict[str, Any]:
        return {
            "componentName": profile.hostname,
            # Calamares 3.3 exige a chave slideshow (QML). O arquivo é copiado
            # do tema padrão no hook de build.
            "slideshow": "show.qml",
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
