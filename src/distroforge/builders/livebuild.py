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
    # configs de módulo (users, bootloader, packages, unpackfs, welcome...);
    # sobrescrevemos settings/packagechooser/netinstall/branding no overlay
    "calamares-settings-debian",
    "squashfs-tools",
    "rsync",
    "parted",
    "efibootmgr",
    "os-prober",
    "sudo",
    # o sistema instalado precisa destes para o bootloader do Calamares.
    # grub-pc e grub-efi-amd64 conflitam entre si; os *-bin convivem.
    "grub-common",
    "grub-pc-bin",
    "grub-efi-amd64-bin",
    "grub-efi-amd64-signed",
    "shim-signed",
    # rede (o firmware vem por base, em FIRMWARE)
    "network-manager",
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

FIRMWARE = {
    "debian": ["firmware-iwlwifi", "firmware-realtek", "firmware-atheros"],
    "ubuntu": ["linux-firmware"],
}

ARCHIVE_AREAS = {
    "debian": "main contrib non-free non-free-firmware",
    "ubuntu": "main restricted universe multiverse",
}

MIRRORS = {
    "debian": "http://deb.debian.org/debian/",
    "ubuntu": "http://archive.ubuntu.com/ubuntu/",
}

SECURITY_MIRRORS = {
    "debian": "http://security.debian.org/debian-security",
    "ubuntu": "http://security.ubuntu.com/ubuntu/",
}

AUTO_CONFIG = """#!/bin/sh
# gerado pelo DistroForge — não edite à mão
set -e
lb config noauto \\
  --mode {mode} \\
  --distribution {distribution} \\
  --mirror-bootstrap {mirror} \\
  --mirror-chroot {mirror} \\
  --mirror-chroot-security {security} \\
  --parent-mirror-bootstrap {mirror} \\
  --parent-mirror-chroot {mirror} \\
  --parent-mirror-chroot-security {security} \\
  --architectures {arch} \\
  --binary-images iso-hybrid \\
  --archive-areas "{areas}" \\
  --bootloaders "syslinux,grub-efi" \\
{extra_options}  --debian-installer none \\
  --memtest none \\
  --apt-indices true \\
  --apt-secure {apt_secure} \\
  --firmware-chroot {firmware} \\
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
  grub-efi-amd64-bin grub-pc-bin grub2-common {extra}

echo "==> lb build"
cd /build
lb build

echo "==> pronto"
ls -lh /build/*.iso
"""

SESSION_HOOK = """#!/bin/sh
# gerado pelo DistroForge — roda a cada boot do live via live-config.
# Tudo aqui é exclusivo da sessão live: nada é criado no sistema instalado.
set -e

# 1) sudo sem senha para o usuário live
cat > /etc/sudoers.d/90-distroforge <<'EOF'
Defaults env_keep += "DISPLAY XAUTHORITY XDG_RUNTIME_DIR"
user ALL=(ALL) NOPASSWD: SETENV: ALL
EOF
chown root:root /etc/sudoers.d/90-distroforge
chmod 0440 /etc/sudoers.d/90-distroforge

# 2) autologin na tty1
install -d /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin user --noclear %I $TERM
EOF

# 3) X confiável mesmo sem seat do logind
cat > /etc/X11/Xwrapper.config <<'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

# 4) cliente X que abre o instalador como root
cat > /usr/local/bin/distroforge-session <<'EOF'
#!/bin/sh
export QT_QPA_PLATFORM=xcb
exec sudo -E sh -c '
  echo "== distroforge: iniciando calamares ==" >/dev/ttyS0
  calamares -d >>/dev/ttyS0 2>&1
  echo "== distroforge: calamares saiu com $? ==" >/dev/ttyS0
'
EOF
chmod 0755 /usr/local/bin/distroforge-session

# 5) startx em qualquer shell de login, com trava de uma tentativa
cat > /etc/profile.d/zz-distroforge-startx.sh <<'EOF'
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ] && [ "$(id -u)" -ne 0 ]; then
  if [ -e /tmp/distroforge-x-tentado ]; then
    echo "DistroForge: o instalador já falhou uma vez; shell liberado para debug."
  else
    : > /tmp/distroforge-x-tentado
    if [ -z "$XDG_RUNTIME_DIR" ] && [ -d "/run/user/$(id -u)" ]; then
      export XDG_RUNTIME_DIR="/run/user/$(id -u)"
    fi
    echo "DistroForge: iniciando o instalador..."
    exec xinit /usr/local/bin/distroforge-session -- :0 vt1
  fi
fi
EOF
chmod 0644 /etc/profile.d/zz-distroforge-startx.sh

# 6) atalho na área de trabalho do usuário live
if [ -d /home/user/Desktop ] && [ -f /usr/share/applications/install-distro.desktop ]; then
  cp /usr/share/applications/install-distro.desktop /home/user/Desktop/ || true
  chown user:user /home/user/Desktop/install-distro.desktop 2>/dev/null || true
fi
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
        distribution = profile.variant or base.build_codename
        mode = "ubuntu" if base.id == "ubuntu" else "debian"
        mirror = MIRRORS.get(base.id, MIRRORS["debian"])
        security = SECURITY_MIRRORS.get(base.id, SECURITY_MIRRORS["debian"])
        # Ubuntu minbase não traz gpgv; incluir é inofensivo no Debian também.
        extra_options = '  --debootstrap-options "--include=gpgv" \\\n' 
        written: list[Path] = []

        written.append(
            self._write(
                workdir / "auto" / "config",
                AUTO_CONFIG.format(
                    mode=mode,
                    areas=ARCHIVE_AREAS.get(base.id, ARCHIVE_AREAS["debian"]),
                    distribution=distribution,
                    mirror=mirror,
                    security=security,
                    extra_options=extra_options,
                    firmware="true" if base.id == "debian" else "false",
                    apt_secure="true" if base.id == "debian" else "false",
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

        packages = list(LIVE_PACKAGES) + FIRMWARE.get(base.id, FIRMWARE["debian"])
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
                includes / "lib" / "live" / "config" / "9999-distroforge",
                SESSION_HOOK,
                executable=True,
            )
        )
        written.append(
            self._write(
                workdir / "build.sh",
                BUILD_SCRIPT.format(extra="ubuntu-keyring" if base.id == "ubuntu" else ""),
                executable=True,
            )
        )
        return written

    def build(
        self,
        profile: Profile,
        workdir: Path,
        *,
        dry_run: bool = False,
        on_line=None,
    ) -> BuildResult:
        command = container_command(DEFAULT_IMAGE, workdir, "build.sh")
        log = workdir / "build.log"

        if dry_run:
            return BuildResult(workdir=workdir, command=command, dry_run=True)

        code = run(command, log, on_line=on_line)
        iso = workdir / f"live-image-{profile.arch}.hybrid.iso"
        return BuildResult(
            workdir=workdir,
            command=command,
            log=log,
            iso=iso if iso.is_file() else None,
            returncode=code,
        )
