#!/usr/bin/env python3
"""Sobe uma ISO no QEMU sem display e captura telas do boot.

Útil para validar a fase 0 sem abrir janela: o script liga a VM, pressiona
Enter no menu do isolinux e tira fotos em intervalos regulares.

Uso:
    python3 scripts/qemu-test.py out/minhadistro-1.0-amd64.iso
    python3 scripts/qemu-test.py out/x.iso --shots-dir /tmp/telas --seconds 180
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


def build_command(iso: Path, sock: Path, memory: int, serial: Path) -> list[str]:
    command = [
        "qemu-system-x86_64",
        "-m",
        str(memory),
        "-smp",
        "2",
        "-cdrom",
        str(iso),
        "-boot",
        "d",
        "-display",
        "none",
        "-vga",
        "std",
        "-monitor",
        f"unix:{sock},server,nowait",
        "-serial",
        f"file:{serial}",
        "-no-reboot",
    ]
    if Path("/dev/kvm").exists():
        command[1:1] = ["-enable-kvm", "-cpu", "host"]
    return command


def connect_monitor(sock: Path, timeout: float = 10.0) -> socket.socket:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sock.exists():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("o monitor do QEMU não abriu")

    connection = socket.socket(socket.AF_UNIX)
    connection.settimeout(10)
    connection.connect(str(sock))
    time.sleep(0.5)
    try:
        connection.recv(65536)
    except TimeoutError:
        pass
    return connection


def hmp(connection: socket.socket, command: str) -> str:
    connection.sendall((command + "\n").encode())
    time.sleep(0.4)
    try:
        return connection.recv(65536).decode(errors="ignore")
    except TimeoutError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--shots-dir", type=Path, default=Path("shots"))
    parser.add_argument("--memory", type=int, default=3072)
    parser.add_argument("--seconds", type=int, default=150, help="duração total do teste")
    parser.add_argument("--keep-ppm", action="store_true")
    args = parser.parse_args()

    iso = args.iso.expanduser().resolve()
    if not iso.is_file():
        print(f"erro: ISO não encontrada: {iso}", file=sys.stderr)
        return 2

    shots = args.shots_dir.resolve()
    shots.mkdir(parents=True, exist_ok=True)
    sock = Path("/tmp/distroforge-qemu.sock")
    serial = shots / "serial.log"
    if sock.exists():
        sock.unlink()

    print(f"subindo {iso.name} …", flush=True)
    process = subprocess.Popen(
        build_command(iso, sock, args.memory, serial),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    try:
        connection = connect_monitor(sock)
    except RuntimeError as error:
        process.kill()
        print(f"erro: {error}", file=sys.stderr)
        return 1

    start = time.time()
    time.sleep(8)
    hmp(connection, "sendkey ret")

    intervals = [40, 30, 35, 40]
    for index, wait in enumerate(intervals[:4], start=1):
        remaining = args.seconds - (time.time() - start)
        if remaining <= 1:
            break
        time.sleep(min(wait, remaining))
        ppm = shots / f"boot{index}.ppm"
        hmp(connection, f"screendump {ppm}")
        elapsed = int(time.time() - start)
        print(f"  captura {index} em {elapsed}s → {ppm}", flush=True)

    hmp(connection, "quit")
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()

    convert = shutil.which("magick") or shutil.which("convert")
    if convert:
        for ppm in sorted(shots.glob("boot*.ppm")):
            png = ppm.with_suffix(".png")
            subprocess.run(
                [convert, str(ppm), str(png)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if png.exists() and not args.keep_ppm:
                ppm.unlink()
            print(f"  png: {png}", flush=True)
    else:
        print("  (ImageMagick não encontrado; telas ficaram em .ppm)", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
