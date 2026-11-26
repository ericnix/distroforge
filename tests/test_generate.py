from __future__ import annotations

from pathlib import Path

import yaml

import pytest

from distroforge.catalog import Catalog, CatalogError
from distroforge.orchestrator import Orchestrator
from distroforge.profile import Profile


@pytest.fixture()
def orchestrator() -> Orchestrator:
    return Orchestrator(Catalog.locate())


@pytest.fixture()
def profile() -> Profile:
    return Profile(
        name="PoC",
        version="1.0",
        base="debian",
        variant="trixie",
        desktop="kde",
        apps=["firefox", "git"],
    )


def _calamares(root, name: str):
    return root / "config" / "includes.chroot" / "etc" / "calamares" / name


def test_gera_arvore_live_build(tmp_path, orchestrator: Orchestrator, profile: Profile):
    generated = orchestrator.generate(profile, tmp_path)
    root = generated.workdir

    assert (root / "auto" / "config").is_file()
    assert (root / "build.sh").is_file()
    assert (root / "config" / "package-lists" / "00-distroforge.list.chroot").is_file()
    assert _calamares(root, "settings.conf").is_file()
    assert _calamares(root, "netinstall.yaml").is_file()
    assert (root / "profile.yaml").is_file()

    config = (root / "auto" / "config").read_text(encoding="utf-8")
    assert "--distribution trixie" in config
    assert "--binary-images iso-hybrid" in config

    menu = (root / "config" / "bootloaders" / "isolinux" / "isolinux.cfg").read_text(
        encoding="utf-8"
    )
    assert "timeout 50" in menu


def test_settings_do_calamares(tmp_path, orchestrator: Orchestrator, profile: Profile):
    root = orchestrator.generate(profile, tmp_path).workdir
    data = yaml.safe_load(_calamares(root, "settings.conf").read_text(encoding="utf-8"))

    show = data["sequence"][0]["show"]
    execute = data["sequence"][1]["exec"]

    assert data["modules-search"] == ["local"]

    part = yaml.safe_load(
        _calamares(root, "modules/partition.conf").read_text(encoding="utf-8")
    )
    assert part["initialSwapChoice"] == "none"
    assert part["defaultFileSystemType"] == "ext4"
    assert "small" in part["userSwapChoices"]
    assert "packagechooser" in show
    assert "netinstall" in show
    assert "packagechooser" not in execute
    assert "unpackfs" in execute
    assert execute.index("unpackfs") < execute.index("bootloader")
    assert data["branding"] == profile.hostname


def test_packagechooser_lista_desktops_da_base(
    tmp_path, orchestrator: Orchestrator, profile: Profile
):
    root = orchestrator.generate(profile, tmp_path).workdir
    data = yaml.safe_load(
        _calamares(root, "modules/packagechooser.conf").read_text(encoding="utf-8")
    )

    names = [item["name"] for item in data["items"]]
    assert "KDE Plasma" in names
    assert "Hyprland" not in names  # indisponível no Debian
    assert len(names) == len(Catalog.locate().graphical_for("debian"))
    assert data["mode"] == "required"
    assert data["method"] == "packages"

    kde = next(item for item in data["items"] if item["name"] == "KDE Plasma")
    assert kde["packages"] == ["task-kde-desktop"]
    assert kde["screenshot"] == "screenshot.png"


def test_netinstall_marca_apps_escolhidos(
    tmp_path, orchestrator: Orchestrator, profile: Profile
):
    root = orchestrator.generate(profile, tmp_path).workdir
    groups = yaml.safe_load(_calamares(root, "netinstall.yaml").read_text(encoding="utf-8"))

    subcategories = {
        item["name"]: item
        for group in groups
        for item in group.get("subgroups", [])
    }
    assert subcategories["Firefox"]["selected"] is True
    assert subcategories["Git"]["selected"] is True
    assert subcategories["Steam"]["selected"] is False
    assert subcategories["Firefox"]["packages"] == ["firefox-esr"]

    # grupos de topo não vêm marcados (senão instalaria tudo)
    assert all(group["selected"] is False for group in groups)


def test_branding_gerado(tmp_path, orchestrator: Orchestrator, profile: Profile):
    root = orchestrator.generate(profile, tmp_path).workdir
    branding = (
        root
        / "config"
        / "includes.chroot"
        / "usr"
        / "share"
        / "calamares"
        / "branding"
        / profile.hostname
        / "branding.desc"
    )
    data = yaml.safe_load(branding.read_text(encoding="utf-8"))
    assert data["strings"]["productName"] == "PoC 1.0"
    assert data["style"]["SidebarBackground"] == "#0b0f1a"
    assert data["slideshow"] == "show.qml"
    assert data["images"]["productLogo"] == "logo.png"
    assert (branding.parent / "logo.png").is_file()
    assert (branding.parent / "welcome.png").is_file()
    assert (branding.parent / "screenshot.png").is_file()
    show = (branding.parent / "show.qml").read_text(encoding="utf-8")
    assert "Instalando PoC 1.0" in show


def test_arquitetura_arch_usa_archiso(tmp_path, orchestrator: Orchestrator):
    profile = Profile(name="ArchPoC", base="arch", desktop="hyprland", apps=["firefox"])
    generated = orchestrator.generate(profile, tmp_path)
    root = generated.workdir

    assert generated.plan.builder == "archiso"
    assert (root / "profile" / "profiledef.sh").is_file()
    assert (root / "profile" / "packages.x86_64").is_file()
    assert (root / "profile" / "airootfs" / "etc" / "calamares" / "settings.conf").is_file()
    assert (
        root / "profile" / "airootfs" / "etc" / "systemd" / "system" / "distroforge-live.service"
    ).is_file()
    link = (
        root
        / "profile"
        / "airootfs"
        / "etc"
        / "systemd"
        / "system"
        / "multi-user.target.wants"
        / "distroforge-live.service"
    )
    assert link.is_symlink()
    assert link.readlink() == Path("/etc/systemd/system/distroforge-live.service")

    pacman = (root / "profile" / "pacman.conf").read_text(encoding="utf-8")
    assert "file:///build/localrepo" in pacman

    packages = (root / "profile" / "packages.x86_64").read_text(encoding="utf-8")
    assert "calamares" in packages


def test_ubuntu_usa_modo_ubuntu_e_espelho_proprio(tmp_path, orchestrator: Orchestrator):
    profile = Profile(name="Ubu", base="ubuntu", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir

    config = (root / "auto" / "config").read_text(encoding="utf-8")
    assert "--mode ubuntu" in config
    assert "--distribution noble" in config
    assert "archive.ubuntu.com" in config
    assert "main restricted universe multiverse" in config
    assert "--linux-flavours generic" in config

    packages = (
        root / "config" / "package-lists" / "00-distroforge.list.chroot"
    ).read_text(encoding="utf-8")
    assert "linux-firmware" in packages
    assert "firmware-iwlwifi" not in packages

    resolv = (root / "config" / "includes.chroot" / "etc" / "resolv.conf").read_text()
    assert "127.0.0.53" not in resolv
    assert "nameserver 1.1.1.1" in resolv

    build = (root / "build.sh").read_text(encoding="utf-8")
    assert "ubuntu-keyring" in build

    # o build desliga apt-secure (userns), mas o alvo recebe fontes assinadas
    assert "--apt-secure false" in config
    sources = (
        root / "config" / "includes.chroot" / "etc" / "apt" / "sources.list"
    ).read_text(encoding="utf-8")
    assert "noble-security" in sources
    assert "trusted=yes" not in sources


def test_packages_conf_sem_live_tasks_no_ubuntu(tmp_path, orchestrator: Orchestrator):
    profile = Profile(name="Ubu", base="ubuntu", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir
    conf = yaml.safe_load(
        _calamares(root, "modules/packages.conf").read_text(encoding="utf-8")
    )
    remove = conf["operations"][0]["remove"]
    assert conf["backend"] == "apt"
    assert "live-task-recommended" not in remove
    assert "live-boot" in remove


def test_packages_conf_com_live_tasks_no_debian(tmp_path, orchestrator: Orchestrator):
    root = orchestrator.generate(Profile(name="Deb", base="debian", desktop="kde"), tmp_path).workdir
    conf = yaml.safe_load(
        _calamares(root, "modules/packages.conf").read_text(encoding="utf-8")
    )
    remove = conf["operations"][0]["remove"]
    assert "live-task-localisation" in remove


def test_ajustes_do_live_nao_vazam_para_o_sistema_instalado(
    tmp_path, orchestrator: Orchestrator, profile: Profile
):
    root = orchestrator.generate(profile, tmp_path).workdir
    includes = root / "config" / "includes.chroot"

    hook = includes / "lib" / "live" / "config" / "9999-distroforge"
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111, "o hook do live-config precisa ser executável"

    # estes só podem existir em tempo de boot do live
    assert not (includes / "etc" / "sudoers.d" / "90-distroforge").exists()
    assert not (includes / "etc" / "skel" / "Desktop" / "install-distro.desktop").exists()

    # o atalho do menu é inofensivo e continua no overlay
    assert (includes / "usr" / "share" / "applications" / "install-distro.desktop").is_file()


def test_build_dry_run_nao_exige_runtime(tmp_path, orchestrator: Orchestrator, profile: Profile):
    result = orchestrator.build(profile, tmp_path / "out", dry_run=True)
    assert result.dry_run is True
    assert result.iso is None
    assert "/build/build.sh" in result.command
    assert result.command[0] in {"podman", "docker"}


def test_force_substitui_arvore_existente(tmp_path, orchestrator: Orchestrator, profile: Profile):
    first = orchestrator.generate(profile, tmp_path)
    with pytest.raises(FileExistsError):
        orchestrator.generate(profile, tmp_path)
    again = orchestrator.generate(profile, tmp_path, force=True)
    assert again.workdir == first.workdir


def test_base_fedora_ainda_sem_adapter(orchestrator: Orchestrator):
    profile = Profile(base="fedora", desktop="kde")
    with pytest.raises(CatalogError, match="anaconda"):
        orchestrator.plan(profile)


def test_aviso_de_repo_externo(tmp_path, orchestrator: Orchestrator):
    profile = Profile(base="debian", desktop="kde", apps=["brave"])
    plan = orchestrator.plan(profile)
    assert any("terceiros" in warning for warning in plan.warnings)


def test_dry_run_debian(tmp_path, orchestrator: Orchestrator, profile: Profile):
    result = orchestrator.build(profile, tmp_path / "saida", dry_run=True)
    command = " ".join(result.command)
    assert "debian:trixie-slim" in command
    assert "--privileged" in command
