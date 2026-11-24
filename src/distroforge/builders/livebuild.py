"""Builder Debian/Ubuntu usando ``live-build``.

Gera um projeto live-build completo: ``auto/config``, lista de pacotes do live,
overlay do instalador, hook de sessão e ``build.sh`` para rodar no container.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..catalog import Catalog, Resolution
from ..container import container_command, run
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
    # rede e firmware (netinstall sem Wi-Fi é inútil)
    "network-manager",
    "firmware-iwlwifi",
    "firmware-realtek",
    "firmware-atheros",
    # sessão gráfica mínima para o Calamares
    "xserver-xorg",
    "xinit",
    "xterm",
    "openbox",
]

AUTO_CONFIG = """\
#!/bin/sh
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
  --apt-indices false \\
  --firmware-chroot true \\
  --bootappend-live "boot=live components quiet splash" \\
  --iso-application "{application}" \\
  --iso-publisher "{publisher}" \\
  --iso-volume "{volume}" \\
  "$@"
"""

BUILD_SCRIPT = """\
#!/usr/bin/env bash
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

SESSION_HOOK = """\
#!/bin/sh
# gerado pelo DistroForge — autostart do Calamares na sessão live (PoC)
set -e

# autologin na tty1 para o usuário criado pelo live-config
install -d /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin user --noclear %I $TERM
EOF

# ao logar na tty1, sobe o X; o .xinitrc abre o instalador
cat > /etc/skel/.bash_profile <<'EOF'
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec startx
fi
EOF

cat > /etc/skel/.xinitrc <<'EOF'
#!/bin/sh
exec calamares
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
                    volume=(profile.hostname.upper()[:30] or "DISTROFORGE"),
                ),
                executable=True,
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
