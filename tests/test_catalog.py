from __future__ import annotations

import shutil

import pytest
import yaml

from distroforge.catalog import Catalog, CatalogError
from distroforge.profile import Profile


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.locate()


def test_catalogo_do_repositorio(catalog: Catalog):
    assert len(catalog.bases) == 5
    assert catalog.base("debian").codename == "trixie"
    assert catalog.base("arch").codename == "rolling"


def test_resolucao_debian_kde(catalog: Catalog):
    profile = Profile(base="debian", desktop="kde", apps=["firefox", "git"])
    resolution = catalog.resolve(profile)

    assert "task-kde-desktop" in resolution.packages
    assert "firefox-esr" in resolution.packages
    assert "git" in resolution.packages
    assert resolution.download_mb == 1850 + 210 + 45
    assert resolution.iso_mb == 780 + 30
    assert resolution.disk_mb > resolution.download_mb


def test_resolucao_arch_usa_pacotes_do_arch(catalog: Catalog):
    profile = Profile(base="arch", desktop="kde", apps=["firefox"])
    resolution = catalog.resolve(profile)
    assert "plasma-meta" in resolution.packages
    assert "firefox" in resolution.packages
    assert "task-kde-desktop" not in resolution.packages


def test_app_desconhecido(catalog: Catalog):
    profile = Profile(base="debian", desktop="kde", apps=["naoexiste"])
    with pytest.raises(CatalogError, match="apps desconhecidos: naoexiste"):
        catalog.resolve(profile)


def test_desktop_indisponivel_na_base(catalog: Catalog):
    profile = Profile(base="fedora", desktop="cinnamon")
    with pytest.raises(CatalogError, match="não está disponível em Fedora"):
        catalog.resolve(profile)


def test_hyprland_nao_existe_no_debian(catalog: Catalog):
    debian = {item.id for item in catalog.graphical_for("debian")}
    arch = {item.id for item in catalog.graphical_for("arch")}
    assert "hyprland" not in debian
    assert "hyprland" in arch


def test_apps_recomendados_debian(catalog: Catalog):
    assert catalog.default_apps("debian") == [
        "firefox",
        "libreoffice",
        "vlc",
        "git",
        "python",
        "htop",
    ]


def test_catalogo_com_base_desconhecida_falha(tmp_path, catalog: Catalog):
    root = tmp_path / "catalog"
    shutil.copytree(catalog.root, root)
    desktops = yaml.safe_load((root / "desktops.yaml").read_text(encoding="utf-8"))
    desktops["desktops"][0]["pkgs"]["gentoo"] = ["kde"]
    (root / "desktops.yaml").write_text(
        yaml.safe_dump(desktops, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    with pytest.raises(CatalogError, match="base desconhecida 'gentoo'"):
        Catalog(root)
