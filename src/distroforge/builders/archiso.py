"""Builder Arch Linux usando ``archiso``.

O Calamares saiu dos repositórios oficiais do Arch: o build compila o pacote
do AUR e o publica num repositório local, que o ``mkarchiso`` consome ao montar
o airootfs.
"""

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
    "syslinux",
    "arch-install-scripts",
    "mkinitcpio-archiso",
    "xorg-server",
    "xorg-xinit",
    "xterm",
    # openbox NÃO entra aqui: o live sobe com `xinit /usr/bin/calamares` e
    # ninguém inicia o window manager. O pacote só embarcaria
    # /usr/share/xsessions/openbox.desktop no sistema instalado, onde o SDDM
    # o escolhe (Openbox < Plasma em ordem alfabética) e o login cai em tela
    # preta. Quem quiser openbox escolhe no packagechooser.
    "dbus",
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
  # o mkarchiso copia o airootfs com `cp --no-preserve=mode`, que descarta os
  # bits de execução; sem isto o systemd falha com 203/EXEC na unit do live.
  ["/usr/local/bin/distroforge-live-setup"]="0:0:755"
)
"""

PACMAN_CONF = """\
[options]
HoldPkg = pacman glibc
Architecture = auto
CheckSpace
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional

[distroforge]
SigLevel = Optional TrustAll
Server = file:///build/localrepo

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist
"""

MKINITCPIO_CONF = """\
MODULES=()
BINARIES=()
FILES=()
HOOKS=(base udev microcode modconf memdisk archiso archiso_loop_mnt archiso_pxe_common archiso_pxe_nbd archiso_pxe_http archiso_pxe_nfs block filesystems keyboard)
COMPRESSION="xz"
COMPRESSION_OPTIONS=(-9e)
"""

SYSLINUX_CFG = """
DEFAULT arch
PROMPT 0
TIMEOUT 150

LABEL arch
MENU LABEL {product}
LINUX /%INSTALL_DIR%/boot/%ARCH%/vmlinuz-linux
INITRD /%INSTALL_DIR%/boot/%ARCH%/initramfs-linux.img
APPEND archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% console=ttyS0,115200 %KERNEL_PARAMS%
"""

LOADER_CONF = """
timeout 10
default 01-distroforge.conf
"""

ENTRY_CONF = """
title    {product} (UEFI)
linux    /%INSTALL_DIR%/boot/%ARCH%/vmlinuz-linux
initrd   /%INSTALL_DIR%/boot/%ARCH%/initramfs-linux.img
options  archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% console=ttyS0,115200 %KERNEL_PARAMS%
"""

BUILD_SCRIPT = """#!/usr/bin/env bash
# gerado pelo DistroForge — roda dentro do container Arch
set -euo pipefail

echo "==> preparando chaves e ferramentas"
pacman-key --init
pacman-key --populate archlinux
pacman -Sy --noconfirm --needed base-devel git archiso

if ls /aur/calamares/*.pkg.tar.* >/dev/null 2>&1; then
  echo "==> calamares do cache (/aur/calamares)"
  mkdir -p /build/pkg/calamares
  cp /aur/calamares/*.pkg.tar.* /build/pkg/calamares/
else
  echo "==> compilando calamares do AUR"
  id -u builder >/dev/null 2>&1 || useradd -m builder
  echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder
  rm -rf /build/pkg
  mkdir -p /build/pkg
  chown builder:builder /build/pkg
  su builder -c '
    set -e
    cd /build/pkg
    git clone --depth 1 https://aur.archlinux.org/calamares.git
    cd calamares
    makepkg -s --noconfirm
  '
  mkdir -p /aur/calamares
  cp /build/pkg/calamares/*.pkg.tar.* /aur/calamares/
fi

echo "==> adaptando pacstrap/arch-chroot para podman rootless"
for f in /usr/bin/arch-chroot /usr/bin/pacstrap; do
  sed -i 's|chroot_add_mount udev "$1/dev" -t devtmpfs -o mode=0755,nosuid|chroot_add_mount /dev "$1/dev" --bind|' "$f"
  sed -i 's|chroot_add_mount devpts "$1/dev/pts" -t devpts -o mode=0620,gid=5,nosuid,noexec|true|' "$f"
  sed -i 's|chroot_add_mount shm "$1/dev/shm" -t tmpfs -o mode=1777,nosuid,nodev|true|' "$f"
  sed -i 's|chroot_add_mount sys "$1/sys" -t sysfs -o nosuid,noexec,nodev,ro|chroot_add_mount /sys "$1/sys" --bind|' "$f"
done

echo "==> publicando repositório local"
mkdir -p /build/localrepo
cp /build/pkg/calamares/*.pkg.tar.* /build/localrepo/
repo-add /build/localrepo/distroforge.db.tar.gz /build/localrepo/*.pkg.tar.*

echo "==> mkarchiso"
mkarchiso -v -w /build/work -o /build/out /build/profile

echo "==> pronto"
ls -lh /build/out/*.iso
"""

# Sessão live: o archiso autologa como root. O instalador sobe direto no X,
# sem sudo. O guarda /run/archiso evita que isso rode no sistema instalado.
LIVE_SERVICE = """\
[Unit]
Description=DistroForge live session
ConditionPathExists=/run/archiso
After=systemd-user-sessions.service
Before=getty@tty1.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/distroforge-live-setup

[Install]
WantedBy=multi-user.target
"""

LIVE_SETUP = """\
#!/bin/sh
# gerado pelo DistroForge — roda apenas no live (ConditionPathExists=/run/archiso)
set -e

install -d /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
EOF

cat > /etc/profile.d/zz-distroforge-startx.sh <<'EOF'
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ] && [ -e /run/archiso ]; then
  if [ -e /tmp/distroforge-x-tentado ]; then
    echo "DistroForge: o instalador já falhou uma vez; shell liberado para debug."
  else
    : > /tmp/distroforge-x-tentado
    echo "DistroForge: iniciando o instalador..."
    exec xinit /usr/bin/calamares -- :0 vt1
  fi
fi
EOF
chmod 0644 /etc/profile.d/zz-distroforge-startx.sh
"""


class ArchisoBuilder(Builder):
    name = "archiso"
    image = DEFAULT_IMAGE

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
        written.append(
            self._write(
                target / "syslinux" / "syslinux.cfg",
                SYSLINUX_CFG.format(product=profile.product_name),
            )
        )
        written.append(self._write(target / "efiboot" / "loader" / "loader.conf", LOADER_CONF))
        written.append(
            self._write(
                target / "efiboot" / "loader" / "entries" / "01-distroforge.conf",
                ENTRY_CONF.format(product=profile.product_name),
            )
        )
        written.append(self._write(target / "packages.x86_64", "\n".join(PACKAGES) + "\n"))

        airootfs = target / "airootfs"
        if overlay.is_dir():
            shutil.copytree(overlay, airootfs, dirs_exist_ok=True)
            written.extend(sorted(path for path in airootfs.rglob("*") if path.is_file()))
        written.append(
            self._write(
                airootfs / "etc" / "mkinitcpio.conf",
                MKINITCPIO_CONF,
            )
        )

        # O systemd-firstboot roda antes de sysinit.target e fica em tty bloqueando
        # o boot inteiro quando falta algo para configurar. É o mesmo conjunto que
        # o releng do archiso traz: sem localtime ele pergunta o timezone, sem
        # locale.conf pergunta o locale e com root travado pergunta a senha.
        written.append(self._write(airootfs / "etc" / "hostname", profile.hostname + "\n"))
        written.append(self._write(airootfs / "etc" / "locale.conf", "LANG=C.UTF-8\n"))
        zoneinfo = airootfs / "etc" / "localtime"
        if zoneinfo.is_symlink() or zoneinfo.exists():
            zoneinfo.unlink()
        zoneinfo.symlink_to("/usr/share/zoneinfo/UTC")
        written.append(zoneinfo)
        # root com senha vazia (não travada) → o firstboot não pergunta.
        written.append(self._write(airootfs / "etc" / "shadow", "root::14871::::::\n"))

        written.append(
            self._write(
                airootfs / "etc" / "systemd" / "system" / "distroforge-live.service",
                LIVE_SERVICE,
            )
        )
        written.append(
            self._write(
                airootfs / "usr" / "local" / "bin" / "distroforge-live-setup",
                LIVE_SETUP,
                executable=True,
            )
        )
        wants = airootfs / "etc" / "systemd" / "system" / "multi-user.target.wants"
        wants.mkdir(parents=True, exist_ok=True)
        for unit, target in (
            ("distroforge-live.service", "/etc/systemd/system/distroforge-live.service"),
            ("NetworkManager.service", "/usr/lib/systemd/system/NetworkManager.service"),
        ):
            link = wants / unit
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(target)
            written.append(link)

        written.append(self._write(workdir / "build.sh", BUILD_SCRIPT, executable=True))
        return written

    def build(
        self,
        profile: Profile,
        workdir: Path,
        *,
        dry_run: bool = False,
        on_line=None,
    ) -> BuildResult:
        cache = Path.home() / ".cache" / "distroforge" / "aur"
        cache.mkdir(parents=True, exist_ok=True)
        command = container_command(
            DEFAULT_IMAGE,
            workdir,
            "build.sh",
            extra_args=["-v", f"{cache}:/aur:Z"],
        )
        log = workdir / "build.log"

        if dry_run:
            return BuildResult(workdir=workdir, command=command, dry_run=True)

        code = run(command, log, on_line=on_line)
        produced = sorted((workdir / "out").glob("*.iso")) if (workdir / "out").is_dir() else []
        return BuildResult(
            workdir=workdir,
            command=command,
            log=log,
            iso=produced[0] if produced else None,
            returncode=code,
        )
