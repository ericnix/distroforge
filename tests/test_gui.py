from __future__ import annotations

from pathlib import Path

import pytest

from distroforge import container


def test_run_emite_linhas_para_callback(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(container, "runtime", lambda: "podman")
    lines: list[str] = []

    code = container.run(
        ["bash", "-c", "printf 'primeira\\nsegunda\\n'"],
        tmp_path / "build.log",
        on_line=lines.append,
    )

    assert code == 0
    assert "primeira" in lines
    assert "segunda" in lines
    logged = (tmp_path / "build.log").read_text(encoding="utf-8").splitlines()
    assert "segunda" in logged


def test_gui_smoke(tmp_path: Path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from distroforge.catalog import Catalog
    from distroforge.gui.app import MainWindow
    from distroforge.gui.theme import STYLESHEET

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)

    window = MainWindow(Catalog.locate(), out_dir=tmp_path)
    try:
        profile = window.current_profile()
        assert profile.base == "debian"
        assert profile.desktop == "kde"
        assert profile.apps

        window._go(1)
        window.state.desktop = "xfce"
        window._refresh()
        assert window.summary.rows["desktop"].text() == "XFCE"

        window._go(0)
        window.state.base = "arch"
        window._on_base_changed()
        assert window.current_profile().base == "arch"
        assert window.state.desktop in {"kde", "gnome", "xfce", "cinnamon", "mate", "lxqt"}
    finally:
        window.close()
