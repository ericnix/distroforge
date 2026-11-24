"""Páginas do assistente."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog, CatalogError
from ..orchestrator import Orchestrator
from ..profile import Profile, ProfileError, slugify
from .theme import ACCENT
from .widgets import OptionCard, SectionTitle


def fmt_mb(mb: int) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB".replace(".", ",")
    return f"{mb} MB"


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class BasePage(QWidget):
    changed = Signal()

    def __init__(self, catalog: Catalog, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.state = state
        self.cards: dict[str, OptionCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        hint = QLabel("A base define os pacotes, o builder e o instalador usados na ISO.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(12)
        for index, base in enumerate(catalog.bases):
            stable = base.is_stable
            card = OptionCard(
                title=base.label,
                description=base.summary,
                badge="" if stable else "em breve",
                meta=f"{base.release} · {base.pkg_manager} · ISO ≈ {fmt_mb(base.iso_size)}",
                enabled=stable,
            )
            if stable:
                card.selected.connect(lambda base_id=base.id: self._pick(base_id))
            self.cards[base.id] = card
            grid.addWidget(card, index // 2, index % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)

        self.cards[state.base].set_checked(True)

    def _pick(self, base_id: str) -> None:
        self.state.base = base_id
        self.changed.emit()


class DesktopPage(QWidget):
    changed = Signal()

    def __init__(self, catalog: Catalog, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.state = state
        self.cards: dict[str, OptionCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        hint = QLabel("Ambientes completos ou window managers — a lista muda conforme a base.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.body = QVBoxLayout(self.container)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(12)
        scroll.setWidget(self.container)
        outer.addWidget(scroll, 1)

        self.load(state.base)

    def load(self, base_id: str) -> None:
        clear_layout(self.body)
        self.cards.clear()

        desktops = self.catalog.desktops_for(base_id)
        wms = self.catalog.wms_for(base_id)

        available = {item.id for item in (*desktops, *wms)}
        if self.state.desktop not in available and available:
            first = desktops[0].id if desktops else wms[0].id
            self.state.desktop = first

        self.body.addWidget(self._group("Ambiente gráfico completo", desktops, base_id, 2))
        if wms:
            self.body.addWidget(self._group("Window managers (você monta o resto)", wms, base_id, 2))
        self.body.addStretch(1)

    def _group(self, title: str, items, base_id: str, columns: int) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle(title))

        grid = QGridLayout()
        grid.setSpacing(10)
        for index, item in enumerate(items):
            card = OptionCard(
                title=item.label,
                description=item.summary,
                meta=f"{fmt_mb(item.size_for(base_id))}" + (f" · {item.note}" if item.note else ""),
            )
            card.selected.connect(lambda item_id=item.id: self._pick(item_id))
            self.cards[item.id] = card
            grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        if self.state.desktop in self.cards:
            self.cards[self.state.desktop].set_checked(True)
        return frame

    def _pick(self, item_id: str) -> None:
        self.state.desktop = item_id
        self.changed.emit()


class AppsPage(QWidget):
    changed = Signal()

    def __init__(self, catalog: Catalog, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.state = state
        self.boxes: dict[str, QCheckBox] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        self.counter = QLabel()
        self.counter.setObjectName("muted")
        toolbar.addWidget(self.counter, 1)

        recommended = QPushButton("Recomendados")
        recommended.clicked.connect(self._select_recommended)
        toolbar.addWidget(recommended)

        clear = QPushButton("Limpar")
        clear.clicked.connect(self._clear)
        toolbar.addWidget(clear)
        outer.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.body = QVBoxLayout(self.container)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(12)
        scroll.setWidget(self.container)
        outer.addWidget(scroll, 1)

        self.load(state.base)

    def load(self, base_id: str) -> None:
        clear_layout(self.body)
        self.boxes.clear()

        available = {app.id for app in self.catalog.apps_for(base_id)}
        self.state.apps &= available
        if not self.state.apps:
            self.state.apps = set(self.catalog.default_apps(base_id))

        for category in self.catalog.categories:
            apps = self.catalog.apps_in(base_id, str(category.get("id")))
            if not apps:
                continue
            frame = QFrame()
            frame.setObjectName("panel")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(6)
            layout.addWidget(SectionTitle(str(category.get("label", ""))))

            grid = QGridLayout()
            grid.setHorizontalSpacing(18)
            grid.setVerticalSpacing(6)
            for index, app in enumerate(apps):
                box = QCheckBox(app.label)
                box.setChecked(app.id in self.state.apps)
                box.toggled.connect(lambda checked, app_id=app.id: self._toggle(app_id, checked))
                size = QLabel(fmt_mb(app.size_for(base_id)))
                size.setObjectName("tiny")
                size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

                row = QHBoxLayout()
                row.addWidget(box, 1)
                row.addWidget(size, 0)
                wrapper = QWidget()
                wrapper.setLayout(row)
                grid.addWidget(wrapper, index // 2, index % 2)

            for column in range(2):
                grid.setColumnStretch(column, 1)
            layout.addLayout(grid)
            self.body.addWidget(frame)

        self.body.addStretch(1)
        self._update_counter()

    def _toggle(self, app_id: str, checked: bool) -> None:
        if checked:
            self.state.apps.add(app_id)
        else:
            self.state.apps.discard(app_id)
        self.changed.emit()
        self._update_counter()

    def _select_recommended(self) -> None:
        self.state.apps = set(self.catalog.default_apps(self.state.base))
        for app_id, box in self.boxes.items():
            box.blockSignals(True)
            box.setChecked(app_id in self.state.apps)
            box.blockSignals(False)
        self.changed.emit()
        self._update_counter()

    def _clear(self) -> None:
        self.state.apps.clear()
        for box in self.boxes.values():
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
        self.changed.emit()
        self._update_counter()

    def _update_counter(self) -> None:
        self.counter.setText(f"{len(self.state.apps)} selecionados")


class DetailsPage(QWidget):
    changed = Signal()

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        card = QFrame()
        card.setObjectName("panel")
        form = QFormLayout(card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name = QLineEdit(state.name)
        self.name.setMaxLength(32)
        self.name.textChanged.connect(self._update_name)
        form.addRow("Nome da distro", self.name)

        self.version = QLineEdit(state.version)
        self.version.setMaxLength(16)
        self.version.textChanged.connect(self._update_version)
        form.addRow("Versão", self.version)

        color_row = QHBoxLayout()
        self.color_button = QPushButton()
        self.color_button.setFixedWidth(90)
        self.color_button.clicked.connect(self._pick_color)
        self.color_label = QLabel(state.color)
        self.color_label.setObjectName("tiny")
        color_row.addWidget(self.color_button)
        color_row.addWidget(self.color_label)
        color_row.addStretch(1)
        color_widget = QWidget()
        color_widget.setLayout(color_row)
        form.addRow("Cor de destaque", color_widget)

        self.preview = QLabel()
        self.preview.setObjectName("muted")
        self.preview.setWordWrap(True)
        form.addRow("", self.preview)

        outer.addWidget(card)
        outer.addStretch(1)

        self._refresh_color()
        self._update_preview()

    def _update_name(self, value: str) -> None:
        self.state.name = value
        self._update_preview()
        self.changed.emit()

    def _update_version(self, value: str) -> None:
        self.state.version = value
        self._update_preview()
        self.changed.emit()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.state.color), self, "Cor de destaque")
        if color.isValid():
            self.state.color = color.name()
            self._refresh_color()
            self.changed.emit()

    def _refresh_color(self) -> None:
        self.color_button.setStyleSheet(
            f"background-color: {self.state.color}; border-radius: 6px; min-height: 18px;"
        )
        self.color_button.setText("")
        self.color_label.setText(self.state.color)

    def _update_preview(self) -> None:
        hostname = slugify(self.state.name or "minhadistro")
        iso = f"{hostname}-{self.state.version or '1.0'}-amd64.iso"
        self.preview.setText(f"hostname: {hostname}\nISO: {iso}")


class SummaryPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setFixedWidth(250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("RESUMO")
        title.setObjectName("eyebrow")
        layout.addWidget(title)

        self.name_label = QLabel("—")
        self.name_label.setObjectName("h2")
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self.hostname_label = QLabel("")
        self.hostname_label.setObjectName("tiny")
        layout.addWidget(self.hostname_label)

        layout.addSpacing(6)
        self.rows: dict[str, QLabel] = {}
        for key, label in (
            ("iso", "ISO"),
            ("download", "Download"),
            ("disk", "No disco"),
            ("base", "Base"),
            ("desktop", "Desktop"),
            ("apps", "Apps"),
        ):
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("muted")
            value = QLabel("—")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(name, 1)
            row.addWidget(value, 0)
            layout.addLayout(row)
            self.rows[key] = value

        self.note = QLabel("")
        self.note.setObjectName("warning")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)

    def set_resolution(self, resolution, profile) -> None:
        self.name_label.setText(profile.product_name)
        self.hostname_label.setText(f"hostname: {profile.hostname}")
        self.rows["iso"].setText(fmt_mb(resolution.iso_mb))
        self.rows["download"].setText(fmt_mb(resolution.download_mb))
        self.rows["disk"].setText(fmt_mb(resolution.disk_mb))
        self.rows["base"].setText(resolution.base.label)
        self.rows["desktop"].setText(resolution.desktop.label)
        self.rows["apps"].setText(str(len(resolution.apps)))
        self.note.setText("")

    def show_error(self, message: str) -> None:
        self.note.setText(message)


class BuildPage(QWidget):
    iso_ready = Signal(str)
    build_requested = Signal()

    def __init__(self, orchestrator: Orchestrator, out_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.out_dir = out_dir
        self.iso: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title = QLabel("Pronto para construir")
        self.title.setObjectName("h2")
        layout.addWidget(self.title)

        self.status = QLabel("Revise o resumo e clique em Construir ISO.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        numbers = QHBoxLayout()
        numbers.setSpacing(10)
        self.metrics: dict[str, QLabel] = {}
        for key, label in (("iso", "ISO"), ("download", "Download"), ("disk", "No disco")):
            frame = QFrame()
            frame.setObjectName("card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 10, 12, 10)
            caption = QLabel(label.upper())
            caption.setObjectName("tiny")
            value = QLabel("—")
            value.setObjectName("h2")
            box.addWidget(caption)
            box.addWidget(value)
            numbers.addWidget(frame, 1)
            self.metrics[key] = value
        layout.addLayout(numbers)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("O log do build aparece aqui.")
        self.log.setMinimumHeight(180)
        layout.addWidget(self.log, 1)

        buttons = QHBoxLayout()
        self.build_button = QPushButton("Construir ISO")
        self.build_button.setObjectName("primary")
        self.build_button.clicked.connect(self.build_requested.emit)
        buttons.addWidget(self.build_button)

        self.qemu_button = QPushButton("Testar no QEMU")
        self.qemu_button.setEnabled(False)
        buttons.addWidget(self.qemu_button)

        self.open_button = QPushButton("Abrir pasta")
        self.open_button.setEnabled(False)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def update_plan(self, resolution) -> None:
        self.metrics["iso"].setText(fmt_mb(resolution.iso_mb))
        self.metrics["download"].setText(fmt_mb(resolution.download_mb))
        self.metrics["disk"].setText(fmt_mb(resolution.disk_mb))

    def set_running(self, running: bool) -> None:
        self.build_button.setEnabled(not running)
        self.progress.setVisible(running)
        if running:
            self.progress.setRange(0, 0)
            self.title.setText("Construindo…")
            self.status.setText("O build roda em container. Isso leva alguns minutos.")
            self.status.setObjectName("muted")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)

    def append(self, line: str) -> None:
        self.log.appendPlainText(line)
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def finished(self, iso: Path) -> None:
        self.iso = iso
        self.title.setText("ISO pronta")
        self.status.setText(str(iso))
        self.status.setObjectName("success")
        self.qemu_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.iso_ready.emit(str(iso))

    def failed(self, message: str) -> None:
        self.title.setText("Build falhou")
        self.status.setText(message)
        self.status.setObjectName("error")
