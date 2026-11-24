#!/usr/bin/env python3
"""Instalação completa numa VM, sem interação manual.

Boota a ISO no QEMU (com disco virtual), dirige o Calamares por VNC e captura
cada etapa. Serve para validar o fluxo inteiro do PoC: partição, usuário,
desktop, netinstall e instalação.

Requer `vncdotool` e `qemu-img`/`qemu-system-x86_64`:

    uv pip install vncdotool
    python3 scripts/qemu-install-test.py out/minha-distro-1.0-amd64.iso

As coordenadas assumem a janela do Calamares em 1280x800 (o padrão do QEMU
`-vga std`); se o tema mudar, ajuste `CLICKS`. A VM continua rodando ao final
para inspeção — encerre com Ctrl+C ou `pkill qemu-system`.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    from vncdotool import api  # type: ignore[import-not-found]
except ImportError:
    sys.exit("erro: instale o vncdotool (uv pip install vncdotool)")

NEXT = (1007, 683)
ERASE_DISK = (311, 163)
FIRST_DESKTOP = (355, 116)
TOGGLE_LOG = (1114, 634)
FIELDS = {
    "name": (403, 146),
    "login": (403, 201),
    "hostname": (403, 258),
    "password": (403, 314),
    "password2": (610, 314),
}


def wait_port(port: int, proc: subprocess.Popen, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit("qemu encerrou antes de abrir o VNC")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise SystemExit("timeout esperando o VNC")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--vm-dir", type=Path, default=Path("vm"))
    parser.add_argument("--vnc", type=int, default=7, help="display VNC (porta 5900+n)")
    parser.add_argument("--memory", type=int, default=3072)
    parser.add_argument("--disk-size", default="20G")
    parser.add_argument("--wait", type=int, default=50, help="segundos até o instalador abrir")
    parser.add_argument("--password", default="distro123")
    parser.add_argument("--no-install", action="store_true", help="para antes do Install")
    args = parser.parse_args()

    iso = args.iso.expanduser().resolve()
    if not iso.is_file():
        sys.exit(f"erro: ISO não encontrada: {iso}")

    vm = args.vm_dir.expanduser().resolve()
    shots = vm / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    disk = vm / "disk.qcow2"
    if disk.exists():
        disk.unlink()
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", str(disk), args.disk_size],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    port = 5900 + args.vnc
    print(f"disco: {disk} ({args.disk_size}) · vnc :{args.vnc} · capturas em {shots}", flush=True)
    qemu = subprocess.Popen(
        [
            "qemu-system-x86_64",
            "-m",
            str(args.memory),
            "-smp",
            "2",
            *(["-enable-kvm", "-cpu", "host"] if Path("/dev/kvm").exists() else []),
            "-cdrom",
            str(iso),
            "-boot",
            "d",
            "-drive",
            f"file={disk},if=virtio,format=qcow2",
            "-display",
            "none",
            "-vga",
            "std",
            "-vnc",
            f"127.0.0.1:{args.vnc}",
            "-serial",
            f"file:{vm}/serial.log",
            "-no-reboot",
        ],
        stdout=open(vm / "qemu.log", "w"),
        stderr=subprocess.STDOUT,
    )

    wait_port(port, qemu)
    print(f"aguardando {args.wait}s o instalador subir…", flush=True)
    time.sleep(args.wait)

    client = api.connect(f"127.0.0.1:{args.vnc}", timeout=60)

    def shot(name: str) -> None:
        client.captureScreen(str(shots / f"{name}.png"))
        print(f"  captura: {name}", flush=True)

    def click(point: tuple[int, int], wait: float = 1.2) -> None:
        client.mouseMove(*point)
        time.sleep(0.2)
        client.mousePress(1)
        time.sleep(wait)

    def type_text(text: str) -> None:
        for char in text:
            client.keyPress(char)
            time.sleep(0.04)

    def fill(point: tuple[int, int], text: str) -> None:
        """Clica, seleciona tudo e digita — o Calamares autopreenche os campos."""
        click(point)
        client.keyPress("ctrl-a")
        type_text(text)

    shot("01-welcome")
    click(NEXT)  # location
    click(NEXT)  # keyboard
    click(NEXT)  # partitions
    shot("02-partitions")
    click(ERASE_DISK)
    click(NEXT)  # users
    shot("03-users")
    click(FIELDS["name"])
    type_text("usuario teste")
    fill(FIELDS["login"], "usuario")
    fill(FIELDS["hostname"], "minha-distro")
    click(FIELDS["password"])
    type_text(args.password)
    click(FIELDS["password2"])
    type_text(args.password)
    click(NEXT)  # desktop
    shot("04-desktop")
    click(FIRST_DESKTOP)
    click(NEXT)  # packages
    shot("05-packages")
    click(NEXT)  # summary
    shot("06-summary")
    if args.no_install:
        print("parando antes do Install (--no-install)", flush=True)
        return 0
    click(NEXT, wait=4)  # install
    shot("07-install-start")
    print("instalando… acompanhe as capturas; a VM segue rodando", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
