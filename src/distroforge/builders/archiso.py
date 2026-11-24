"""Builder Arch Linux usando ``archiso``."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..catalog import Catalog, Resolution
from ..container import container_command, run
from ..labels import iso_volume_label
from ..profile import Profile
from .base import Builder, BuildResult

DEFAULT_IMAGE = "archlinux:latest"

PACKAGES = [
    "base",
    "linux",
    "linux-firmware",
    "mkinitcpio",
    "systemd",
    "sudo",
    "networkmanager",
    "iwd",
    "calamares",
    "squashfs-tools",
    "rsync",
    "parted",
    "gptfdisk",
    "dosfstools",
    "mtools",
    "efibootmgr",
    "grub",
    "arch-install-scripts",
    "xorg-server",
    "xorg-xinit",
    "xterm",
    "openbox",
]

PROFILEDEF = """\
#!/usr/bin/env bash
# gerado pelo DistroForge — não edite à mão
iso_name="{iso_name}"
iso_label="{iso_label}"
iso_publisher="{publisher}"
iso_application="{application}"
iso_version="{version}"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux' 'uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=parallel' '--long=31')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
)
"""

PACMAN_CONF = """\
[options]
HoldPkg = pacman glibc
Architecture = auto
CheckSpace
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist

[multilib]
Include = /etc/pacman.d/mirrorlist
"""

BUILD_SCRIPT = """\
#!/usr/bin/env bash
# gerado pelo DistroForge — roda dentro do container Arch
set -euo pipefail

echo "==> instalando archiso"
pacman -Sy --noconfirm --needed archiso

echo "==> mkarchiso"
mkarchiso -v -w /build/work -o /build/out /build/profile

echo "==> pronto"
ls -lh /build/out/*.iso
"""

SESSION_HOOK = """\
#!/bin/sh
# gerado pelo DistroForge — autostart do Calamares na sessão live (PoC)
set -e
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


class ArchisoBuilder(Builder):
    name = "archiso"

    def prepare(
        self,
        profile: Profile,
        resolution: Resolution,
        catalog: Catalog,
        workdir: Path,
        overlay: Path,
    ) -> list[Path]:
        target = workdir / "profile"
        written: list[Path] = []

        label = iso_volume_label(profile.hostname, max_len=11)

        written.append(
            self._write(
                target / "profiledef.sh",
                PROFILEDEF.format(
                    iso_name=profile.hostname,
                    iso_label=label,
                    publisher=f"DistroForge — {profile.name}",
                    application=profile.product_name,
                    version=profile.version,
                ),
                executable=True,
            )
        )
        written.append(self._write(target / "pacman.conf", PACMAN_CONF))
        written.append(self._write(target / "packages.x86_64", "\n".join(PACKAGES) + "\n"))

        airootfs = target / "airootfs"
        if overlay.is_dir():
            shutil.copytree(overlay, airootfs, dirs_exist_ok=True)
            written.extend(sorted(path for path in airootfs.rglob("*") if path.is_file()))

        written.append(
            self._write(
                target / "airootfs" / "etc" / "local.d" / "distroforge-session.sh",
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
        produced = sorted((workdir / "out").glob("*.iso")) if (workdir / "out").is_dir() else []
        return BuildResult(
            workdir=workdir,
            command=command,
            log=log,
            iso=produced[0] if produced else None,
            returncode=code,
        )
