"""Tema escuro da GUI (mesma paleta do site)."""

from __future__ import annotations

INK = "#06070b"
PANEL = "#0b0e15"
PANEL_ALT = "#0f131c"
BORDER = "#1d2331"
BORDER_SOFT = "#262e3f"
TEXT = "#e9ecf5"
MUTED = "#8d96ad"
MUTED_DIM = "#6f788d"
ACCENT = "#4f8ef7"
ACCENT_SOFT = "#2f6fe0"
GREEN = "#4ade9b"
AMBER = "#f2b45a"
RED = "#f4708f"

STYLESHEET = f"""
QWidget {{
    background-color: {INK};
    color: {TEXT};
    font-size: 13px;
}}
QLabel, QCheckBox, QRadioButton, QGroupBox, QListWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}
QMainWindow, QDialog {{
    background-color: {INK};
}}
QFrame#panel {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#card {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#card[selected="true"] {{
    border: 1px solid {ACCENT};
    background-color: #101a2e;
}}
QFrame#card[disabled="true"] {{
    background-color: #0a0c11;
}}
QLabel#h1 {{ font-size: 22px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#tiny {{ color: {MUTED_DIM}; font-size: 11px; }}
QLabel#eyebrow {{
    color: {ACCENT};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#success {{ color: {GREEN}; }}
QLabel#warning {{ color: {AMBER}; }}
QLabel#error {{ color: {RED}; }}
QRadioButton {{ spacing: 8px; font-weight: 600; }}
QRadioButton::indicator {{
    width: 14px; height: 14px;
    border-radius: 7px;
    border: 2px solid {BORDER_SOFT};
    background: transparent;
}}
QRadioButton::indicator:checked {{
    border: 4px solid {ACCENT};
    background: {INK};
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border-radius: 4px;
    border: 1px solid {BORDER_SOFT};
    background: {INK};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}
QPushButton {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background-color: {BORDER}; }}
QPushButton:disabled {{ color: {MUTED_DIM}; background-color: #0a0c11; }}
QPushButton#primary {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: {INK};
    font-weight: 700;
}}
QPushButton#primary:hover {{ background-color: #6ea2ff; }}
QPushButton#primary:disabled {{ background-color: {BORDER_SOFT}; color: {MUTED_DIM}; }}
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: 9px 10px;
    border-radius: 8px;
    color: {MUTED};
    margin: 1px 0;
}}
QListWidget::item:selected {{
    background-color: #101a2e;
    color: {TEXT};
    border-left: 2px solid {ACCENT};
}}
QListWidget::item:hover {{ background-color: {PANEL_ALT}; }}
QPlainTextEdit {{
    background-color: #07090e;
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: #b9c2d6;
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 11px;
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {PANEL_ALT};
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 5px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_SOFT}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QLineEdit {{
    background: {INK};
    border: 1px solid {BORDER_SOFT};
    border-radius: 7px;
    padding: 7px 9px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {MUTED};
}}
QToolTip {{
    background: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER_SOFT};
    padding: 4px;
}}
"""
