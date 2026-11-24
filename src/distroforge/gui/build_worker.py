"""Thread de build: mantém a interface viva enquanto o container roda."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..orchestrator import Orchestrator
from ..profile import Profile


class BuildWorker(QThread):
    line = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, orchestrator: Orchestrator, profile: Profile, out_dir: Path) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.profile = profile
        self.out_dir = out_dir

    def run(self) -> None:  # noqa: D401 (executado na thread)
        try:
            result = self.orchestrator.build(
                self.profile,
                self.out_dir,
                force=True,
                on_line=self.line.emit,
            )
        except Exception as error:  # noqa: BLE001 — a GUI mostra qualquer falha
            self.failed.emit(str(error))
            return
        if result.iso is None:
            self.failed.emit("o build terminou sem gerar ISO")
            return
        self.succeeded.emit(str(result.iso))
