"""Widgets reutilizáveis da GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class OptionCard(QFrame):
    """Cartão selecionável com rádio, título, descrição e metadados."""

    selected = Signal()

    def __init__(
        self,
        title: str,
        description: str = "",
        badge: str = "",
        meta: str = "",
        enabled: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setProperty("selected", False)
        self.setProperty("disabled", not enabled)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.radio = QRadioButton(title)
        self.radio.setEnabled(enabled)
        header.addWidget(self.radio, 1)
        if badge:
            badge_label = QLabel(badge)
            badge_label.setObjectName("tiny")
            badge_label.setStyleSheet(
                "border: 1px solid #2a3142; border-radius: 8px; padding: 2px 7px;"
            )
            header.addWidget(badge_label, 0)
        layout.addLayout(header)

        if description:
            self.description = QLabel(description)
            self.description.setObjectName("muted")
            self.description.setWordWrap(True)
            layout.addWidget(self.description)

        self.meta = QLabel(meta)
        self.meta.setObjectName("tiny")
        layout.addWidget(self.meta)

        self.radio.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.setProperty("selected", checked)
        self._repolish()
        if checked:
            self.selected.emit()

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (API Qt)
        if self.radio.isEnabled():
            self.radio.setChecked(True)
        super().mousePressEvent(event)

    def set_checked(self, checked: bool) -> None:
        self.radio.setChecked(checked)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("h2")
