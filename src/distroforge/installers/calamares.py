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
    # networkcfg omitido de propósito: ele copia o symlink do resolved do live
    # por cima do nosso resolv.conf (o nsswitch/resolv do overlay resolvem o DNS)
    "hwclock",
    # netinstall/packages ANTES de services-systemd: no Arch o display
    # manager vem do netinstall (plasma-meta puxa plasma-login-manager) e os
    # pacotes Arch não se habilitam sozinhos. Habilitar antes de instalar
    # faz o `systemctl enable plasmalogin.service` falhar com "unit not
    # found" — e a falha é suprimida por a unit ser não-mandatória.
    # Confirmado no sistema instalado: `systemctl is-enabled
    # display-manager.service` → not-found, e o boot caía no getty.
    # No Ubuntu é no-op (não geramos services-systemd.conf lá).
    "netinstall",
    "packages",
    "services-systemd",
    "initramfscfg",
    "initramfs",
    "bootloader",
    "umount",
]

# Dois preparos que o alvo precisa ANTES do job `packages`:
#
# 1. keyring do pacman: o `pacman-key --init` do build roda no CONTAINER,
#    então o squashfs sai sem /etc/pacman.d/gnupg. Sem ele o `pacman -S`
#    morre em "required key missing from keyring" (testado no alvo: o
#    `pacman -Sy` passa porque os DBs são DatabaseOptional, mas os pacotes
#    exigem assinatura). Pior: o backend pacman usa
#    target_env_process_output, que não propaga o erro — o Calamares
#    mostra "Done" e nada é instalado.
# 2. /boot: o mkarchiso apaga o /boot do airootfs antes do squashfs, então
#    o alvo nasce sem /boot/vmlinuz-linux. O preset do mkinitcpio passa
#    `-k /boot/vmlinuz-linux` e morre com "must be readable"; o
#    grub-mkconfig não acha nenhum kernel e não gera entrada de boot.
#    O kernel está em /usr/lib/modules/<kver>/vmlinuz.
#
# dontChroot: false (default) = roda `chroot <alvo> /bin/sh -c`, com /proc,
# /sys e /dev já montados pelo mount.conf (extraMounts).
# Sem `$` de propósito: o expander do shellprocess usa `$` como símbolo de
# macro e trataria qualquer `$var` como variável não definida (erro).
# timeout alto: o pacman-key --init gera a chave mestra (demora).
SHELLPROCESS_BOOT = {
    "dontChroot": False,
    "timeout": 180,
    "verbose": True,
    "script": [
        "mkdir -p /boot && cp -f /usr/lib/modules/*/vmlinuz /boot/vmlinuz-linux",
        "pacman-key --init",
        "pacman-key --populate archlinux",
    ],
}

# O Calamares empacotado por base nem sempre é o upstream. O do AUR (3.4.2)
# não traz todos os módulos: não há ``packagechooser`` (a escolha do desktop
# entra no netinstall) e os módulos de initramfs se chamam ``initcpiocfg`` /
# ``initcpio``. Usar os nomes do Debian lá aborta o instalador com
# "Calamares Initialization Failed" listando os módulos ausentes.
MODULE_ALIASES: dict[str, dict[str, str]] = {
    "arch": {"initramfscfg": "initcpiocfg", "initramfs": "initcpio"},
}
MISSING_MODULES: dict[str, set[str]] = {"arch": {"packagechooser"}}

# ``pacman -R`` aborta a transação inteira se algum pacote da lista não
# existir; ``try_remove`` tira um a um e só avisa. Nas bases apt o ``remove``
# já está validado de ponta a ponta.
REMOVE_OPERATION = {"apt": "remove", "pacman": "try_remove"}

# O AUR traz `internetCheckUrl: http://example.com` — uma URL só, e ela é
# ponto único de falha: se o domínio não resolver (DNS da empresa, bloqueio
# regional, quarentena), a página marca "not connected" e `hasInternet` fica
# false para sempre. É `hasInternet` que libera o `pacman -Sy` do módulo
# packages, então uma URL fora do ar derrubaria a instalação inteira com
# "target not found" (o alvo sai do squashfs sem /var/lib/pacman/sync).
# O Calamares aceita lista e considera a rede OK se qualquer uma responder.
WELCOME_CONF = """\
---
showSupportUrl:         true
showKnownIssuesUrl:     true
showReleaseNotesUrl:    false
showDonateUrl:          https://kde.org/community/donations/
requirements:
    requiredStorage:    5.5
    requiredRam:        1.0
    internetCheckUrl:
        - https://distroforge-site.pages.dev
        - https://archlinux.org
        - http://example.org
    check:
        - storage
        - ram
        - power
        - internet
        - root
        - screen
    required:
        - ram
geoip:
    style:    "none"
    url:      "https://geoip.kde.org/v1/ubiquity"
    selector: "CountryCode"
"""


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

# Particionamento explícito: sem isto o módulo usa defaults do binário,
# que no Ubuntu geram só swap e deixam o disco sem partição raiz.
# Pacotes do live a remover do sistema instalado. Os live-task-* só existem
# no Debian; no Ubuntu o apt-get remove deles retorna código 100.
LIVE_REMOVAL = {
    "debian": [
        "live-boot",
        "live-boot-doc",
        "live-config",
        "live-config-doc",
        "live-config-systemd",
        "live-tools",
        "live-task-localisation",
        "live-task-recommended",
        "calamares-settings-debian",
    ],
    "ubuntu": [
        "live-boot",
        "live-boot-doc",
        "live-config",
        "live-config-doc",
        "live-config-systemd",
        "live-tools",
        "calamares-settings-debian",
    ],
    # No Arch o equivalente são os pacotes de construção da ISO e os hooks do
    # archiso. O mkinitcpio-archiso sai antes do initcpio rodar, e o
    # initcpiocfg reescreve o HOOKS do alvo de qualquer forma. dosfstools e
    # mtools ficam: o alvo precisa deles para partitionar/formatar de novo.
    "arch": [
        "mkinitcpio-archiso",
        "arch-install-scripts",
        "squashfs-tools",
    ],
}

PARTITION_CONF = {
    "defaultFileSystemType": "ext4",
    "initialSwapChoice": "none",
    "userSwapChoices": ["none", "small"],
    # Layout explícito: sem isto o Ubuntu não criava a partição raiz.
    "partitionLayout": [
        {
            "name": "rootfs",
            "filesystem": "ext4",
            "mountPoint": "/",
            "size": "100%",
        }
    ],
    "efi": {
        "mountPoint": "/boot/efi",
        "recommendedSize": "300MiB",
        "minimumSize": "32MiB",
    },
    "lvm": {"enable": True},
}

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
        written.append(
            self._write_yaml(
                calamares / "settings.conf",
                self._settings(profile, base_id, resolution.base.pkg_manager),
            )
        )
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
        written.append(self._write_yaml(modules / "partition.conf", PARTITION_CONF))
        pkg_manager = resolution.base.pkg_manager
        if pkg_manager in REMOVE_OPERATION:
            if pkg_manager == "apt":
                removal = LIVE_REMOVAL.get(base_id, LIVE_REMOVAL["debian"])
            else:
                removal = LIVE_REMOVAL.get(base_id, [])
            operation = REMOVE_OPERATION[pkg_manager]
            operations = [{operation: removal}] if removal else []
            config: dict[str, Any] = {"backend": pkg_manager, "operations": operations}
            if pkg_manager == "pacman":
                # o alvo sai do squashfs sem /var/lib/pacman/sync: sem um -Sy
                # prévio o `pacman -S` falha com "target not found". No apt as
                # lists do live já vêm prontas, então não mexemos no validado.
                config["update_db"] = True
            written.append(self._write_yaml(modules / "packages.conf", config))
        if "packagechooser" not in MISSING_MODULES.get(base_id, set()):
            written.append(
                self._write_yaml(
                    modules / "packagechooser.conf",
                    self._packagechooser(profile, resolution, catalog),
                )
            )
        if pkg_manager == "pacman":
            # O AUR traz uma checagem de rede de URL única (não resolvia aqui
            # e derrubava a instalação); a nossa aceita lista.
            written.append(self._write(modules / "welcome.conf", WELCOME_CONF))
            # Põe o kernel em /boot do alvo (o squashfs sai sem /boot).
            written.append(
                self._write_yaml(modules / "shellprocess.conf", SHELLPROCESS_BOOT)
            )
            # No Debian/Ubuntu o postinst do sddm habilita a própria unit; no
            # Arch o preset do systemd é `disable *` e ninguém habilita nada —
            # o sistema instalado subiria no getty, sem tela de login.
            # Lista de candidatos: só a que existir é habilitada, e o módulo
            # suprime silenciosamente as falhas de units não-mandatórias.
            written.append(
                self._write_yaml(
                    modules / "services-systemd.conf",
                    {
                        "units": [
                            "plasmalogin.service",
                            "sddm.service",
                            "gdm.service",
                            "lightdm.service",
                        ]
                    },
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
    def _settings(
        profile: Profile, base_id: str = "debian", pkg_manager: str = "apt"
    ) -> dict[str, Any]:
        aliases = MODULE_ALIASES.get(base_id, {})
        missing = MISSING_MODULES.get(base_id, set())

        def adapt(sequence: list[str]) -> list[str]:
            out = []
            for name in sequence:
                if name in missing:
                    continue
                out.append(aliases.get(name, name))
            return out

        execute = adapt(EXEC_SEQUENCE)
        if pkg_manager == "pacman":
            # Precisa rodar antes do packages: é ele que inicializa o keyring
            # (sem ele o `pacman -S` morre em "required key missing from
            # keyring") e põe o kernel em /boot (sem ele o mkinitcpio morre
            # no `-k` e o grub-mkconfig não gera entrada de boot).
            execute.insert(execute.index("packages"), "shellprocess")

        return {
            # "local" resolve para <libdir>/calamares/modules, onde o Debian
            # instala os módulos (multiarch). Sem esta chave a lista fica vazia
            # e nenhum módulo é encontrado.
            "modules-search": ["local"],
            "instances": [],
            "sequence": [
                {"show": adapt(SHOW_SEQUENCE)},
                {"exec": execute},
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

        # Sem `packagechooser` (Arch) ninguém entrega os pacotes do desktop:
        # o netinstall vira o único lugar onde o usuário escolhe o ambiente
        # gráfico. No Debian/Ubuntu o packagechooser cuida disso e uma segunda
        # escolha aqui seria redundante.
        if "packagechooser" in MISSING_MODULES.get(resolution.base.id, set()):
            desktops = []
            for item in catalog.graphical_for(resolution.base.id):
                size = item.size_for(resolution.base.id)
                description = item.summary
                if size:
                    description = f"{description} ({_fmt_mb(size)})"
                desktops.append(
                    {
                        "name": item.label,
                        "description": description,
                        "packages": item.packages(resolution.base.id),
                        "selected": item.id == profile.desktop,
                    }
                )
            if desktops:
                groups.append(
                    {
                        "name": "Ambiente gráfico",
                        "description": "Escolha o desktop que será instalado",
                        "selected": False,
                        "expanded": True,
                        "subgroups": desktops,
                    }
                )

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
