"""Builder Debian/Ubuntu usando ``live-build``.

Gera um projeto live-build completo: ``auto/config``, lista de pacotes do live,
overlay do instalador, hook de sessão e ``build.sh`` para rodar no container.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..catalog import Catalog, Resolution
from ..container import container_command, run
from ..labels import iso_volume_label
from ..profile import Profile
from .base import Builder, BuildResult

DEFAULT_IMAGE = "debian:trixie-slim"

LIVE_PACKAGES = [
    # instalador e ferramentas
    "calamares",
    "squashfs-tools",
    "rsync",
    "parted",
    "efibootmgr",
    "os-prober",
    "sudo",
    # o sistema instalado precisa destes para o bootloader do Calamares
    "grub-pc",
    "grub-efi-amd64",
    "grub-efi-amd64-signed",
    "shim-signed",
    # rede e firmware (netinstall sem Wi-Fi é inútil)
    "network-manager",
    "firmware-iwlwifi",
    "firmware-realtek",
    "firmware-atheros",
    # sessão gráfica mínima para o Calamares
    "xserver-xorg",
    "xserver-xorg-legacy",
    "xinit",
    "xterm",
    "openbox",
    "dbus",
]

# O live-build (1:20250505) não expõe opção de timeout de menu; sobrescrever o
# template é o mecanismo documentado. timeout é em décimos de segundo.
BOOTLOADER_ISOLINUX_CFG = """include menu.cfg
default vesamenu.c32
prompt 0
timeout 50
"""

AUTO_CONFIG = """#!/bin/sh
# gerado pelo DistroForge — não edite à mão
set -e
lb config noauto \\
  --distribution {distribution} \\
  --architectures {arch} \\
  --binary-images iso-hybrid \\
  --archive-areas "main contrib non-free non-free-firmware" \\
  --bootloaders "syslinux,grub-efi" \\
  --debian-installer none \\
  --memtest none \\
  --apt-indices true \\
  --firmware-chroot true \\
  --bootappend-live "boot=live components quiet splash autologin console=ttyS0,115200 systemd.journald.forward_to_console=1" \\
  --iso-application "{application}" \\
  --iso-publisher "{publisher}" \\
  --iso-volume "{volume}" \\
  "$@"
"""

BUILD_SCRIPT = """#!/usr/bin/env bash
# gerado pelo DistroForge — roda dentro do container Debian
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "==> instalando ferramentas de build"
apt-get update
apt-get install -y --no-install-recommends \\
  live-build xorriso squashfs-tools mtools dosfstools rsync \\
  wget ca-certificates git syslinux syslinux-common isolinux \\
  grub-efi-amd64-bin grub-pc-bin grub2-common

echo "==> lb build"
cd /build
lb build

echo "==> pronto"
ls -lh /build/*.iso
"""

SESSION_HOOK = """#!/bin/sh
# gerado pelo DistroForge — autostart do Calamares na sessão live (PoC)
set -e

# 1) autologin na tty1
install -d /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin user --noclear %I $TERM
EOF

# 2) sudo sem senha (não depende do live-config)
cat > /etc/sudoers.d/90-distroforge <<'EOF'
Defaults env_keep += "DISPLAY XAUTHORITY XDG_RUNTIME_DIR"
user ALL=(ALL) NOPASSWD: SETENV: ALL
EOF
chown root:root /etc/sudoers.d/90-distroforge
chmod 0440 /etc/sudoers.d/90-distroforge

# 3) X pode rodar como usuário comum mesmo sem seat do logind
cat > /etc/X11/Xwrapper.config <<'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

# 3b) cliente X que abre o instalador como root
cat > /usr/local/bin/distroforge-session <<'EOF'
#!/bin/sh
export QT_QPA_PLATFORM=xcb
exec sudo -E QT_QPA_PLATFORM=xcb calamares
EOF
chmod 0755 /usr/local/bin/distroforge-session

# 4) startx em qualquer shell de login (bash, dash, zsh) + trava de 1 tentativa
cat > /etc/profile.d/zz-distroforge-startx.sh <<'EOF'
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ] && [ "$(id -u)" -ne 0 ]; then
  if [ -e /run/distroforge-x-tentado ]; then
    echo "DistroForge: o instalador já falhou uma vez; shell liberado para debug."
  else
    : > /run/distroforge-x-tentado
    echo "DistroForge: iniciando o instalador..."
    # a saída vai para o console serial, onde o teste de boot consegue ler
    exec xinit /usr/local/bin/distroforge-session -- :0 vt1 >>/dev/ttyS0 2>&1
  fi
fi
EOF
chmod 0644 /etc/profile.d/zz-distroforge-startx.sh

# 5) atalhos para uma sessão interativa
cat >> /etc/skel/.bash_profile <<'EOF'

# DistroForge: abre o instalador na sessão live
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec startx
fi
EOF

cat > /etc/skel/.xinitrc <<'EOF'
#!/bin/sh
exec sudo -E calamares
EOF
chmod +x /etc/skel/.xinitrc
"""


class LiveBuildBuilder(Builder):
    name = "live-build"

    def prepare(
        self,
        profile: Profile,
        resolution: Resolution,
        catalog: Catalog,
        workdir: Path,
        overlay: Path,
    ) -> list[Path]:
        base = resolution.base
        distribution = profile.variant or base.codename
        written: list[Path] = []

        written.append(
            self._write(
                workdir / "auto" / "config",
                AUTO_CONFIG.format(
                    distribution=distribution,
                    arch=profile.arch,
                    application=profile.name,
                    publisher=f"DistroForge — {profile.name}",
                    volume=iso_volume_label(profile.hostname),
                ),
                executable=True,
            )
        )

        written.append(
            self._write(
                workdir / "config" / "bootloaders" / "isolinux" / "isolinux.cfg",
                BOOTLOADER_ISOLINUX_CFG,
            )
        )

        packages = list(LIVE_PACKAGES)
        if base.id == "ubuntu":
            # Ubuntu precisa de pacotes próprios na sessão live
            packages.append("kubuntu-installer-prompt")
        written.append(
            self._write(
                workdir / "config" / "package-lists" / "00-distroforge.list.chroot",
                "\n".join(packages) + "\n",
            )
        )

        includes = workdir / "config" / "includes.chroot"
        if overlay.is_dir():
            shutil.copytree(overlay, includes, dirs_exist_ok=True)
            written.extend(sorted(path for path in includes.rglob("*") if path.is_file()))

        written.append(
            self._write(
                workdir / "config" / "hooks" / "live" / "0100-distroforge-session.chroot",
                SESSION_HOOK,
                executable=True,
            )
        )
        written.append(self._write(workdir / "build.sh", BUILD_SCRIPT, executable=True))
        return written

    def build(
        self,
        profile: Profile,
        workdir: Path,
        *,
        dry_run: bool = False,
    ) -> BuildResult:
        command = container_command(DEFAULT_IMAGE, workdir, "build.sh")
        log = workdir / "build.log"

        if dry_run:
            return BuildResult(workdir=workdir, command=command, dry_run=True)

        code = run(command, log)
        iso = workdir / f"live-image-{profile.arch}.hybrid.iso"
        return BuildResult(
            workdir=workdir,
            command=command,
            log=log,
            iso=iso if iso.is_file() else None,
            returncode=code,
        )
