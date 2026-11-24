"""Execução em container: o build nunca suja o host.

Cada base roda no seu habitat (Debian, Arch, ...) e o diretório de trabalho é
montado em ``/build``. É preciso ``--privileged`` porque ``lb build`` e
``mkarchiso`` criam loop devices e fazem mounts dentro do chroot.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class ContainerError(RuntimeError):
    pass


def runtime() -> str | None:
    """Devolve ``podman`` ou ``docker``, o que estiver disponível."""
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    return None


def require_runtime() -> str:
    found = runtime()
    if found is None:
        raise ContainerError(
            "podman (ou docker) não encontrado; instale um deles para rodar o build"
        )
    return found


def container_command(
    image: str,
    workdir: Path,
    script: str,
    *,
    extra_args: list[str] | None = None,
    engine: str | None = None,
) -> list[str]:
    # Em dry-run o comando é só exibido, então não exigimos o runtime aqui.
    runner = engine or runtime() or "podman"
    return [
        runner,
        "run",
        "--rm",
        "--privileged",
        "-v",
        f"{workdir.resolve()}:/build:Z",
        "-w",
        "/build",
        "-e",
        "DEBIAN_FRONTEND=noninteractive",
        *(extra_args or []),
        image,
        "bash",
        f"/build/{script}",
    ]


def remove_tree(path: Path) -> None:
    """Remove uma árvore que pode ter arquivos criados dentro do container.

    Em podman rootless, processos não-root do container gravam com subuids, e o
    usuário do host não consegue apagar. Nesse caso removemos de dentro do
    container, onde esses uids são mapeados.
    """
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
        return
    except PermissionError:
        pass

    engine = runtime()
    if engine is None:
        raise ContainerError(
            f"sem permissão para remover {path} e podman/docker não está disponível"
        )

    parent = path.resolve().parent
    completed = subprocess.run(
        [
            engine,
            "run",
            "--rm",
            "-v",
            f"{parent}:/w:Z",
            "debian:trixie-slim",
            "rm",
            "-rf",
            f"/w/{path.name}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0 or path.exists():
        raise ContainerError(
            f"não foi possível remover {path}: {completed.stderr.strip()}"
        )


def run(command: list[str], log_path: Path) -> int:
    """Roda o comando, ecoando a saída e gravando tudo no log."""
    if runtime() is None:
        raise ContainerError(
            "podman (ou docker) não encontrado; instale um deles para rodar o build"
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        header = "$ " + " ".join(command) + "\n"
        log.write(header)
        log.flush()

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as error:
            raise ContainerError(f"não foi possível executar {command[0]}: {error}") from error
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
        return process.wait()
