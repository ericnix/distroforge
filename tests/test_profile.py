from __future__ import annotations

import pytest

from distroforge.profile import Profile, ProfileError, slugify

SITE_PROFILE = """
meta:
  name: "MinhaDistro"
  version: "1.0"
  hostname: "Minha Distro!"
base: debian
variant: "13 (trixie)"
arch: amd64
install_mode: netinstall
desktop_default: kde
apps_default: [firefox, vlc, firefox]
branding:
  color: "#3b82f6"
  iso_name: "minhadistro-1.0-amd64.iso"
offline_fallback: minimal
"""


def test_slugify_remove_acentos_e_espacos():
    assert slugify("Minha Distro Ágil") == "minha-distro-agil"
    assert slugify("!!!") == "minhadistro"


def test_perfil_no_formato_do_site():
    profile = Profile.from_dict(
        {
            "meta": {"name": "MinhaDistro", "version": "1.0", "hostname": "minhadistro"},
            "base": "arch",
            "variant": "rolling",
            "arch": "amd64",
            "install_mode": "netinstall",
            "desktop_default": "kde",
            "apps_default": ["firefox", "git"],
            "branding": {"color": "#1793d1", "iso_name": "minhadistro-1.0-amd64.iso"},
        }
    )
    assert profile.base == "arch"
    assert profile.desktop == "kde"
    assert profile.apps == ["firefox", "git"]
    assert profile.iso_name == "minhadistro-1.0-amd64.iso"


def test_hostname_e_iso_derivados_do_nome():
    profile = Profile(name="Minha Distro", base="debian", desktop="kde")
    assert profile.hostname == "minha-distro"
    assert profile.iso_name == "minha-distro-1.0-amd64.iso"


def test_apps_duplicados_sao_removidos_mantendo_ordem():
    profile = Profile(
        base="debian", desktop="kde", apps=["vlc", "firefox", "vlc", "git", "firefox"]
    )
    assert profile.apps == ["vlc", "firefox", "git"]


def test_yaml_ida_e_volta():
    original = Profile(
        name="Teste", base="debian", desktop="xfce", apps=["vlc"], color="#112233"
    )
    clone = Profile.from_dict(
        __import__("yaml").safe_load(original.to_yaml())
    )
    assert clone.to_dict() == original.to_dict()


def test_base_invalida():
    with pytest.raises(ProfileError, match="base 'gentoo' inválida"):
        Profile(base="gentoo", desktop="kde")


def test_cor_invalida():
    with pytest.raises(ProfileError, match="cor de branding"):
        Profile(base="debian", desktop="kde", color="azul")


def test_le_perfil_do_site_com_comentarios(tmp_path):
    file = tmp_path / "profile.yaml"
    file.write_text(SITE_PROFILE, encoding="utf-8")
    profile = Profile.from_file(file)
    assert profile.apps == ["firefox", "vlc"]
    assert profile.hostname == "minha-distro"


def test_arquivo_inexistente():
    with pytest.raises(ProfileError, match="perfil não encontrado"):
        Profile.from_file("/tmp/nao-existe-distroforge.yaml")
