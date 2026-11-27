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


def test_arch_tem_python_para_os_modulos_do_calamares():
    """O calamares do AUR linka libpython mas não declara a dependência.

    Sem ``python`` o binário falha com ``libpython3.14.so.1.0 => not found``
    e o Xorg sai com código 0 — a tela fica preta sem nenhum erro óbvio.
    """
    from distroforge.builders.archiso import PACKAGES

    assert "python" in PACKAGES


def test_arch_traz_os_arquivos_do_firstboot(tmp_path, orchestrator: Orchestrator):
    """O systemd-firstboot roda antes de sysinit.target e trava o boot.

    Sem ``localtime`` ele pergunta o timezone, sem ``locale.conf`` pergunta o
    locale e com o root travado pergunta a senha — tudo bloqueando o live em
    um prompt no console. É o mesmo conjunto que o releng do archiso traz.
    """
    profile = Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir
    etc = root / "profile" / "airootfs" / "etc"

    assert (etc / "hostname").read_text(encoding="utf-8").strip()
    assert "LANG=" in (etc / "locale.conf").read_text(encoding="utf-8")
    localtime = etc / "localtime"
    assert localtime.is_symlink() and str(localtime.readlink()) == "/usr/share/zoneinfo/UTC"

    # root com campo de senha vazio (não "!") → o firstboot não pergunta
    shadow = (etc / "shadow").read_text(encoding="utf-8")
    assert shadow.startswith("root::")

    # o mkarchiso copia com `cp --no-preserve=mode` e descarta os bits de
    # execução; sem file_permissions a unit do live falha com 203/EXEC
    profiledef = (root / "profile" / "profiledef.sh").read_text(encoding="utf-8")
    assert '["/usr/local/bin/distroforge-live-setup"]="0:0:755"' in profiledef

    # o systemd carrega as units na transação de boot, antes do script rodar;
    # sem daemon-reload ele ignora o drop-in de autologin do tty1
    setup = (etc.parent / "usr" / "local" / "bin" / "distroforge-live-setup").read_text(
        encoding="utf-8"
    )
    assert "systemctl daemon-reload" in setup
    assert "--autologin root" in setup


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

    nsswitch = (root / "config" / "includes.chroot" / "etc" / "nsswitch.conf").read_text()
    assert "files dns" in nsswitch
    assert "resolve" not in nsswitch

    # a live precisa gerenciar a placa ethernet para o netinstall ter rede
    nm = (
        root / "config" / "includes.chroot" / "usr" / "lib" / "NetworkManager"
        / "conf.d" / "10-globally-managed-devices.conf"
    ).read_text()
    assert "unmanaged-devices=" in nm
    assert "except:type" not in nm

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


def _calamares_arch(root, name: str):
    """No Arch o overlay vai para profile/airootfs, não config/includes.chroot."""
    return root / "profile" / "airootfs" / "etc" / "calamares" / name


def test_arch_usa_os_modulos_que_o_calamares_do_aur_tem(tmp_path, orchestrator: Orchestrator):
    """O Calamares do AUR não tem ``packagechooser`` e nomeia o initramfs outro jeito.

    A sequência do Debian aborta lá com "Calamares Initialization Failed"
    listando ``packagechooser``, ``initramfscfg`` e ``initramfs`` — e sem o
    packagechooser o netinstall ficaria sem entregar o desktop.
    """
    profile = Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir
    data = yaml.safe_load(_calamares_arch(root, "settings.conf").read_text(encoding="utf-8"))

    show = data["sequence"][0]["show"]
    execute = data["sequence"][1]["exec"]

    assert "packagechooser" not in show
    assert "netinstall" in show
    assert "initramfscfg" not in execute and "initramfs" not in execute
    assert execute.index("initcpiocfg") < execute.index("initcpio")
    assert execute.index("initcpio") < execute.index("bootloader")
    # o módulo inexistente não deve deixar config órfã
    assert not _calamares_arch(root, "modules/packagechooser.conf").exists()


def test_arch_instala_o_disco_sem_backend_dummy(tmp_path, orchestrator: Orchestrator):
    """Sem ``packages.conf`` o Calamares cai no default ``backend: dummy``.

    O dummy só loga: o netinstall escolheria os pacotes e nada seria
    instalado — nem o desktop, nem os apps. E o alvo sai do squashfs sem
    ``/var/lib/pacman/sync``, então o ``-Sy`` é obrigatório.
    """
    profile = Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir
    conf = yaml.safe_load(
        _calamares_arch(root, "modules/packages.conf").read_text(encoding="utf-8")
    )

    assert conf["backend"] == "pacman"
    assert conf["update_db"] is True
    # pacman -R aborta a transação inteira se faltar um pacote
    assert conf["operations"][0]["try_remove"] == [
        "mkinitcpio-archiso",
        "arch-install-scripts",
        "squashfs-tools",
    ]


def test_arch_escolhe_o_desktop_pelo_netinstall(tmp_path, orchestrator: Orchestrator):
    """Sem packagechooser, o netinstall é o único lugar onde o desktop é escolhido."""
    profile = Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir
    groups = yaml.safe_load(_calamares_arch(root, "netinstall.yaml").read_text(encoding="utf-8"))

    desktop_group = next(g for g in groups if g["name"] == "Ambiente gráfico")
    names = [item["name"] for item in desktop_group["subgroups"]]
    assert "KDE Plasma" in names

    kde = next(item for item in desktop_group["subgroups"] if item["name"] == "KDE Plasma")
    assert kde["selected"] is True
    assert kde["packages"] == ["plasma-meta", "kde-applications"]
    # só um desktop marcado
    assert sum(1 for i in desktop_group["subgroups"] if i["selected"]) == 1


def test_arch_habilita_o_display_manager_no_alvo(tmp_path, orchestrator: Orchestrator):
    """No Arch o preset do systemd é ``disable *``: sem isto o alvo sobe no getty.

    No Debian/Ubuntu o postinst do sddm habilita a própria unit, por isso
    só as bases pacman precisam deste módulo.
    """
    profile = Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"])
    root = orchestrator.generate(profile, tmp_path).workdir
    conf = yaml.safe_load(
        _calamares_arch(root, "modules/services-systemd.conf").read_text(encoding="utf-8")
    )
    units = [u if isinstance(u, str) else u["name"] for u in conf["units"]]

    assert "plasmalogin.service" in units
    assert "sddm.service" in units


def test_services_systemd_roda_depois_de_instalar(
    tmp_path, orchestrator: Orchestrator, profile: Profile
):
    """No Arch o display manager vem do netinstall, e pacotes Arch não se
    habilitam sozinhos.

    Habilitar antes de instalar faz o `systemctl enable plasmalogin.service`
    falhar — e a falha é suprimida por a unit ser não-mandatória. Confirmado
    no sistema instalado: `systemctl is-enabled display-manager.service` →
    not-found, e o boot caía no getty em vez do display manager.
    """
    root = orchestrator.generate(profile, tmp_path).workdir
    data = yaml.safe_load(_calamares(root, "settings.conf").read_text(encoding="utf-8"))
    execute = data["sequence"][1]["exec"]

    assert execute.index("packages") < execute.index("services-systemd")


def test_arch_copia_o_kernel_para_boot_antes_do_mkinitcpio(
    tmp_path, orchestrator: Orchestrator
):
    """Dois preparos que o alvo precisa ANTES do job `packages`.

    **keyring**: o `pacman-key --init` do build roda no container, então o
    squashfs sai sem /etc/pacman.d/gnupg. Sem ele o `pacman -S` morre em
    "required key missing from keyring" — e o backend pacman usa
    target_env_process_output, que não propaga o erro, então o Calamares
    mostra "Done" sem instalar nada (testado no alvo).

    **/boot**: o mkarchiso apaga o /boot do airootfs antes do squashfs, então
    o alvo nasce sem /boot/vmlinuz-linux. O preset do mkinitcpio passa
    `-k /boot/vmlinuz-linux` e morre com "must be readable" (também testado
    no alvo); o grub-mkconfig não acha nenhum kernel e não gera entrada de
    boot.
    """
    root = orchestrator.generate(
        Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"]),
        tmp_path,
    ).workdir
    data = yaml.safe_load(_calamares_arch(root, "settings.conf").read_text(encoding="utf-8"))
    execute = data["sequence"][1]["exec"]

    assert "shellprocess" in execute
    # os dois preparos precisam rodar antes do packages e do initramfs
    for later in ("packages", "initcpiocfg", "initcpio", "bootloader"):
        assert execute.index("shellprocess") < execute.index(later)

    conf = yaml.safe_load(
        _calamares_arch(root, "modules/shellprocess.conf").read_text(encoding="utf-8")
    )
    script = " ".join(conf["script"])
    assert "/boot/vmlinuz-linux" in script
    assert "/usr/lib/modules" in script
    assert "pacman-key --init" in script
    assert "pacman-key --populate" in script
    # o mkarchiso apaga o sync db, e o update_db do packages é condicionado
    # a `hasInternet` — rodamos o -Sy aqui, fora dessa dependência
    assert "pacman -Sy" in script
    # sem `$`: o expander do shellprocess usa `$` como símbolo de macro
    assert "$" not in script
    # roda DENTRO do chroot do alvo (dontChroot: false é o default)
    assert conf["dontChroot"] is False


def test_ubuntu_nao_recebe_shellprocess_nem_mirrorlist(
    tmp_path, orchestrator: Orchestrator, profile: Profile
):
    """O live-build do Debian mantém o /boot e o apt já resolve os mirrors."""
    root = orchestrator.generate(profile, tmp_path).workdir
    data = yaml.safe_load(_calamares(root, "settings.conf").read_text(encoding="utf-8"))

    assert "shellprocess" not in data["sequence"][1]["exec"]
    assert not _calamares(root, "modules/shellprocess.conf").exists()


def test_arch_tem_mirror_ativo_no_alvo(tmp_path, orchestrator: Orchestrator):
    """O pacman-mirrorlist vem com TODOS os servidores comentados.

    Quem instala é esperado escrever o próprio mirror (o archinstall faz; o
    mkarchiso não toca no arquivo). Com tudo comentado o `pacman -Sy` falha
    com "no servers configured for repository" dentro do chroot e o job
    `packages` do Calamares aborta a instalação. O build não cai nisso
    porque o Include resolve no container, que tem a mirrorlist da imagem.
    """
    root = orchestrator.generate(
        Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"]),
        tmp_path,
    ).workdir
    mirror = root / "profile" / "airootfs" / "etc" / "pacman.d" / "mirrorlist"

    active = [
        l for l in mirror.read_text(encoding="utf-8").splitlines()
        if l.startswith("Server")
    ]
    assert len(active) >= 1, "nenhum Server ativo: pacman -Sy vai falhar"
    assert all("$repo" in l for l in active)


def test_arch_tem_nameserver_no_alvo(tmp_path, orchestrator: Orchestrator):
    """O squashfs sai com o /etc/resolv.conf do systemd — só comentários.

    No live o NetworkManager reescreve em runtime, mas o alvo recebe o
    arquivo do squashfs, e o Calamares não copia o do host. Sem nameserver o
    `pacman -Sy` do módulo packages falha com código 1 dentro do chroot e a
    instalação aborta em "Package Manager error".
    """
    root = orchestrator.generate(
        Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"]),
        tmp_path,
    ).workdir
    resolv = root / "profile" / "airootfs" / "etc" / "resolv.conf"

    assert resolv.is_file() and not resolv.is_symlink()
    text = resolv.read_text(encoding="utf-8")
    assert "nameserver" in text
    assert len([l for l in text.splitlines() if l.startswith("nameserver")]) >= 2


def test_arch_tem_sudo_para_o_job_do_calamares():
    """O módulo `users` do Calamares escreve /etc/sudoers.

    Sem o pacote `sudo` o arquivo não existe, o job falha com "Cannot create
    sudoers file for writing." e a instalação inteira cai em emergência — o
    bootloader nem chega a rodar. No Debian/Ubuntu o sudo entra no live por
    padrão, então só o Arch precisa declarar.
    """
    from distroforge.builders.archiso import PACKAGES

    assert "sudo" in PACKAGES


def test_arch_espera_a_rede_antes_de_subir_o_instalador(
    tmp_path, orchestrator: Orchestrator
):
    """A checagem de rede do welcome roda uma vez e grava `hasInternet`.

    É ela que libera o `pacman -Sy` do módulo packages. Se o X subir antes
    do NetworkManager pegar IP, a página marca "not connected" e a
    instalação morre em "target not found" — o alvo sai do squashfs sem
    /var/lib/pacman/sync.
    """
    root = orchestrator.generate(
        Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"]),
        tmp_path,
    ).workdir
    setup = (
        root / "profile" / "airootfs" / "usr" / "local" / "bin" / "distroforge-live-setup"
    ).read_text(encoding="utf-8")

    assert "nm-online" in setup
    # precisa esperar conectividade plena, não só o startup do NM
    assert "nm-online -q --timeout" in setup
    assert "nm-online -s" not in setup
    # sem rede o instalador continua, só sem poder baixar pacotes
    assert "exec xinit /usr/bin/calamares" in setup
    assert setup.index("nm-online") < setup.index("exec xinit")


def test_arch_nao_depende_de_uma_url_sola_na_checagem_de_rede(
    tmp_path, orchestrator: Orchestrator
):
    """O AUR traz `internetCheckUrl: http://example.com` — uma URL só.

    Aqui esse domínio não resolve, a página marcava "not connected" e
    `hasInternet` ficava false: sem ele o `pacman -Sy` não roda e a
    instalação morre em "target not found" (o alvo sai do squashfs sem
    /var/lib/pacman/sync). Lista de URLs = qualquer uma respondendo basta.
    """
    root = orchestrator.generate(
        Profile(name="ArchPoC", base="arch", desktop="kde", apps=["firefox"]),
        tmp_path,
    ).workdir
    conf = yaml.safe_load(
        _calamares_arch(root, "modules/welcome.conf").read_text(encoding="utf-8")
    )

    urls = conf["requirements"]["internetCheckUrl"]
    assert isinstance(urls, list) and len(urls) >= 2
    assert all(u.startswith(("http://", "https://")) for u in urls)
    assert "internet" in conf["requirements"]["check"]


def test_ubuntu_nao_recebe_services_systemd_do_arch(
    tmp_path, orchestrator: Orchestrator, profile: Profile
):
    """Lá o postinst do DM cuida da unit; lista extra é ruído."""
    root = orchestrator.generate(profile, tmp_path).workdir
    assert not _calamares(root, "modules/services-systemd.conf").exists()


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


def test_todas_as_bases_declararam_uma_fonte():
    """Nenhuma base pode depender de fonte entrar por acidente de dependência.

    No Debian/Ubuntu ``fonts-dejavu-core`` vinha implícito no
    ``calamares-settings-debian``; no Arch não vinha nada e a UI do
    Calamares saiu inteira em caixas vazias (tofu), sem erro no Xorg além
    de um ``(WW) The directory "/usr/share/fonts/TTF" does not exist``.
    """
    from distroforge.builders.archiso import PACKAGES as arch_packages
    from distroforge.builders.livebuild import LIVE_PACKAGES

    assert "fontconfig" in arch_packages
    assert any(p.startswith(("ttf-", "noto-")) for p in arch_packages)
    assert any(p.startswith("fonts-") for p in LIVE_PACKAGES)


def test_live_sem_window_manager_que_vaze_sessao_para_o_alvo():
    """O live sobe com `xinit`, que só executa o Calamares.

    Ninguém inicia um window manager no live, então um pacote como ``openbox``
    seria peso morto — e pior: ele embarca ``/usr/share/xsessions/openbox.desktop``
    no squashfs, que vai parar no sistema instalado. Com duas sessões o SDDM
    escolhe a primeira em ordem alfabética (Openbox < Plasma) e o usuário cai
    em tela preta após o login.
    """
    from distroforge.builders.archiso import PACKAGES as arch_packages
    from distroforge.builders.livebuild import LIVE_PACKAGES

    assert "openbox" not in LIVE_PACKAGES
    assert "openbox" not in arch_packages


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
