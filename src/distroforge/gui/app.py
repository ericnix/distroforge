"""Janela principal do DistroForge."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog, CatalogError
from ..orchestrator import Orchestrator
from ..profile import Profile, ProfileError, slugify
from .build_worker import BuildWorker
from .pages import AppsPage, BasePage, BuildPage, DesktopPage, DetailsPage, SummaryPanel
from .qemu import launch_qemu
from .theme import ACCENT, MUTED, STYLESHEET

STEPS = [
    ("Base", "De onde a distro herda pacotes e atualizações."),
    ("Desktop", "O ambiente gráfico que o usuário final vê."),
    ("Programas", "Apps baixados do repositório na instalação."),
    ("Personalizar", "Nome, versão e cor da sua distro."),
    ("Construir", "Resumo, build em container e teste no QEMU."),
]


@dataclass
class GuiState:
    base: str = "debian"
    desktop: str = "kde"
    apps: set[str] = field(default_factory=set)
    name: str = "Minha Distro"
    version: str = "1.0"
    color: str = ACCENT


class MainWindow(QMainWindow):
    def __init__(self, catalog: Catalog, out_dir: Path | None = None) -> None:
        super().__init__()
        self.catalog = catalog
        self.orchestrator = Orchestrator(catalog)
        self.state = GuiState(apps=set(catalog.default_apps("debian")))
        self.out_dir = out_dir or Path.cwd() / "out"
        self.worker: BuildWorker | None = None

        self.setWindowTitle("DistroForge")
        self.resize(1120, 760)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)
        self.setCentralWidget(central)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)
        self.summary = SummaryPanel()
        root.addWidget(self.summary)

        self._refresh()
        self._go(0)

    # ------------------------------------------------------------- construção

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("panel")
        side.setFixedWidth(206)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(4)

        brand = QLabel("DistroForge")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        brand.setFont(font)
        layout.addWidget(brand)

        subtitle = QLabel("construtor de distros")
        subtitle.setObjectName("tiny")
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self.steps = QListWidget()
        self.steps.setFocusPolicy(Qt.NoFocus)
        for index, (name, _) in enumerate(STEPS, start=1):
            item = QListWidgetItem(f"{index}. {name}")
            item.setSizeHint(QSize(0, 34))
            self.steps.addItem(item)
        self.steps.currentRowChanged.connect(self._go)
        layout.addWidget(self.steps, 1)

        note = QLabel("Fase 2 · GUI")
        note.setObjectName("tiny")
        layout.addWidget(note)
        return side

    def _build_main(self) -> QWidget:
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(10)

        self.header = QLabel()
        self.header.setObjectName("h1")
        layout.addWidget(self.header)

        self.header_sub = QLabel()
        self.header_sub.setObjectName("muted")
        self.header_sub.setWordWrap(True)
        layout.addWidget(self.header_sub)

        self.stack = QStackedWidget()

        self.base_page = BasePage(self.catalog, self.state)
        self.base_page.changed.connect(self._on_base_changed)

        self.desktop_page = DesktopPage(self.catalog, self.state)
        self.desktop_page.changed.connect(self._refresh)

        self.apps_page = AppsPage(self.catalog, self.state)
        self.apps_page.changed.connect(self._refresh)

        self.details_page = DetailsPage(self.state)
        self.details_page.changed.connect(self._refresh)

        self.build_page = BuildPage(self.orchestrator, self.out_dir)
        self.build_page.build_requested.connect(self._start_build)

        for page in (
            self.base_page,
            self.desktop_page,
            self.apps_page,
            self.details_page,
            self.build_page,
        ):
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.back_button = QPushButton("Voltar")
        self.back_button.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        footer.addWidget(self.back_button)
        footer.addStretch(1)
        self.next_button = QPushButton("Continuar")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(lambda: self._go(self.stack.currentIndex() + 1))
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        return main

    # ---------------------------------------------------------------- estado

    def current_profile(self) -> Profile:
        base = self.catalog.base(self.state.base)
        return Profile(
            name=self.state.name.strip() or "MinhaDistro",
            version=self.state.version.strip() or "1.0",
            base=base.id,
            variant=base.build_codename,
            desktop=self.state.desktop,
            apps=sorted(self.state.apps),
            color=self.state.color,
        )

    def _on_base_changed(self) -> None:
        self.desktop_page.load(self.state.base)
        self.apps_page.load(self.state.base)
        self._refresh()

    def _refresh(self) -> None:
        try:
            profile = self.current_profile()
            resolution = self.catalog.resolve(profile)
        except (CatalogError, ProfileError) as error:
            self.summary.show_error(str(error))
            self.next_button.setEnabled(False)
            return

        self.summary.set_resolution(resolution, profile)
        self.build_page.update_plan(resolution)
        self.next_button.setEnabled(True)

    # ------------------------------------------------------------ navegação

    def _go(self, index: int) -> None:
        index = max(0, min(index, len(STEPS) - 1))
        if self.steps.currentRow() != index:
            self.steps.blockSignals(True)
            self.steps.setCurrentRow(index)
            self.steps.blockSignals(False)

        self.stack.setCurrentIndex(index)
        name, description = STEPS[index]
        self.header.setText(name)
        self.header_sub.setText(description)
        self.back_button.setEnabled(index > 0)
        self.next_button.setVisible(index < len(STEPS) - 1)
        if index == len(STEPS) - 2:
            self.next_button.setText("Ir para o build")
        else:
            self.next_button.setText("Continuar")
        if index == len(STEPS) - 1:
            self._refresh()

    # ---------------------------------------------------------------- build

    def _start_build(self) -> None:
        try:
            profile = self.current_profile()
            self.orchestrator.plan(profile)
        except (CatalogError, ProfileError) as error:
            QMessageBox.warning(self, "Perfil inválido", str(error))
            return

        if self.worker is not None and self.worker.isRunning():
            return

        self.build_page.log.clear()
        self.build_page.set_running(True)
        self.next_button.setEnabled(False)

        self.worker = BuildWorker(self.orchestrator, profile, self.out_dir)
        self.worker.line.connect(self.build_page.append)
        self.worker.succeeded.connect(self._build_succeeded)
        self.worker.failed.connect(self._build_failed)
        self.worker.start()

    def _build_succeeded(self, iso: str) -> None:
        self.build_page.set_running(False)
        self.build_page.finished(Path(iso))
        self.next_button.setEnabled(True)

    def _build_failed(self, message: str) -> None:
        self.build_page.set_running(False)
        self.build_page.failed(message)
        self.next_button.setEnabled(True)
        QMessageBox.critical(self, "Build falhou", message)

    def _test_qemu(self) -> None:
        iso = self.build_page.iso
        if iso is None or not iso.is_file():
            return
        try:
            launch_qemu(iso)
        except (RuntimeError, OSError) as error:
            QMessageBox.critical(self, "QEMU", str(error))

    def _open_folder(self) -> None:
        iso = self.build_page.iso
        folder = iso.parent if iso is not None else self.out_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("DistroForge")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    try:
        catalog = Catalog.locate()
    except CatalogError as error:
        QMessageBox.critical(None, "DistroForge", str(error))
        return 1

    window = MainWindow(catalog)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
