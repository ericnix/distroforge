"""Abrir a ISO gerada numa VM, direto pela interface."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def launch_qemu(iso: Path) -> subprocess.Popen:
    """Sobe o QEMU com a ISO e um disco virtual de 20 GB."""
    qemu = shutil.which("qemu-system-x86_64")
    if qemu is None:
        raise RuntimeError("qemu-system-x86_64 não encontrado; instale o QEMU")
    if shutil.which("qemu-img") is None:
        raise RuntimeError("qemu-img não encontrado; instale o QEMU")

    disk = Path.home() / ".cache" / "distroforge" / "vm" / "disk.qcow2"
    disk.parent.mkdir(parents=True, exist_ok=True)
    if not disk.exists():
        subprocess.run(
            ["qemu-img", "create", "-f", "qcow2", str(disk), "20G"],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    command = [qemu, "-m", "3072", "-smp", "2"]
    if Path("/dev/kvm").exists():
        command += ["-enable-kvm", "-cpu", "host"]
    command += [
        "-cdrom",
        str(iso),
        "-boot",
        "d",
        "-drive",
        f"file={disk},if=virtio,format=qcow2",
    ]
    return subprocess.Popen(command)
