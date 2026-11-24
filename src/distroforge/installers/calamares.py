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
from .artwork import gradient_png
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
    "initramfscfg",
    "initramfs",
    "bootloader",
    "umount",
]


SHOW_QML = """import QtQuick

Rectangle {{
    id: root
    color: "{color}"

    Column {{
        anchors.centerIn: parent
        spacing: 18

        Text {{
            anchors.horizontalCenter: parent.horizontalCenter
            color: "#7aa7ff"
            font.pixelSize: 15
            font.letterSpacing: 2
            text: "DISTROFORGE"
        }}

        Text {{
            anchors.horizontalCenter: parent.horizontalCenter
            color: "#e9ecf5"
            font.pixelSize: 22
            text: qsTr("Instalando {product}…")
        }}

        Text {{
            anchors.horizontalCenter: parent.horizontalCenter
            color: "#6f788d"
            font.pixelSize: 13
            text: qsTr("Isso pode levar alguns minutos.")
        }}
    }}
}}
"""

DESKTOP_TEMPLATE = """[Desktop Entry]
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
        written.extend(self._branding_images(profile, branding))
        written.append(
            self._write(
                overlay / "usr" / "share" / "applications" / "install-distro.desktop",
                DESKTOP_TEMPLATE.format(product=profile.product_name),
            )
        )
        return written

    # ------------------------------------------------------------- seções

    @staticmethod
    def _settings(profile: Profile) -> dict[str, Any]:
        return {
            # "local" resolve para <libdir>/calamares/modules, onde o Debian
            # instala os módulos (multiarch). Sem esta chave a lista fica vazia
            # e nenhum módulo é encontrado.
            "modules-search": ["local"],
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
        """Estrutura mínima aceita pelo Calamares 3.3.

        Nós e chaves ausentes (``images``, ``slideshow``) abortam o instalador
        com FATAL; os nomes de ``style`` são capitalizados.
        """
        return {
            "componentName": profile.hostname,
            "welcomeStyleCalamares": True,
            "welcomeExpandingLogo": True,
            "windowExpanding": "normal",
            "windowSize": "860px,600px",
            "windowPlacement": "center",
            "strings": {
                "productName": profile.product_name,
                "shortProductName": profile.name,
                "version": profile.version,
                "shortVersion": profile.version,
                "versionedName": profile.product_name,
                "shortVersionedName": profile.product_name,
                "bootloaderEntryName": profile.name,
                "productUrl": "https://distroforge-site.pages.dev",
                "supportUrl": "https://github.com/ericnix/distroforge/issues",
                "knownIssuesUrl": "https://github.com/ericnix/distroforge/issues",
                "releaseNotesUrl": "https://github.com/ericnix/distroforge/blob/main/docs/PLAN.md",
                "donateUrl": "",
            },
            "sidebar": "widget",
            "navigation": "widget",
            "images": {
                "productLogo": "logo.png",
                "productIcon": "logo.png",
                "productWelcome": "welcome.png",
            },
            # O QML é copiado do tema padrão no hook de build.
            "slideshow": "show.qml",
            "slideshowAPI": 2,
            "style": {
                "SidebarBackground": "#0b0f1a",
                "SidebarText": "#e9ecf5",
                "SidebarTextCurrent": "#ffffff",
                "SidebarBackgroundCurrent": profile.color,
            },
        }

    @staticmethod
    def _branding_images(profile: Profile, branding: Path) -> list[Path]:
        """Escreve logo, boas-vindas, miniatura e o QML do slideshow."""
        branding.mkdir(parents=True, exist_ok=True)
        images = {
            "logo.png": gradient_png(
                256, 256, "#16233d", "#0a0f19", accent=profile.color, accent_rows=(0.55, 0.62)
            ),
            "welcome.png": gradient_png(
                860, 600, "#0b1120", "#16233d", accent=profile.color, accent_rows=(0.74, 0.79)
            ),
            "screenshot.png": gradient_png(
                160, 90, "#0b1120", "#1b2a4a", accent=profile.color, accent_rows=(0.72, 0.85)
            ),
        }
        written: list[Path] = []
        for name, payload in images.items():
            path = branding / name
            path.write_bytes(payload)
            written.append(path)

        show = branding / "show.qml"
        show.write_text(
            SHOW_QML.format(color="#0b0f1a", product=profile.product_name),
            encoding="utf-8",
        )
        written.append(show)
        return written

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
