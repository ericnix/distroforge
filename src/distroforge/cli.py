"""Interface de linha de comando do DistroForge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .builders.base import BuildError
from .catalog import Catalog, CatalogError, Resolution
from .container import ContainerError
from .orchestrator import Orchestrator, Plan
from .profile import ARCHES, BASES, INSTALL_MODES, Profile, ProfileError


# ------------------------------------------------------------------ formatação

def _color(code: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def dim(text: str) -> str:
    return _color("2", text)


def bold(text: str) -> str:
    return _color("1", text)


def green(text: str) -> str:
    return _color("32", text)


def blue(text: str) -> str:
    return _color("36", text)


def yellow(text: str) -> str:
    return _color("33", text)


def fmt_mb(mb: int) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB".replace(".", ",")
    return f"{mb} MB"


def _row(key: str, value: str) -> str:
    return f"  {dim(key.ljust(10))} {value}"


def print_plan(plan: Plan) -> None:
    profile = plan.profile
    resolution: Resolution = plan.resolution

    print()
    print(f"  {bold(profile.product_name)}  {dim('· ' + profile.hostname)}")
    print(_row("base", f"{resolution.base.label} {resolution.base.release}".strip()))
    print(_row("builder", plan.builder))
    print(_row("installer", plan.installer))
    print(_row("distro", plan.distribution))
    print(_row("arch", profile.arch))

    desktop_size = resolution.desktop.size_for(resolution.base.id)
    print(_row("desktop", f"{resolution.desktop.label}  {dim(fmt_mb(desktop_size))}"))
    apps_size = sum(app.size_for(resolution.base.id) for app in resolution.apps)
    print(
        _row(
            "apps",
            f"{len(resolution.apps)} selecionados  {dim(fmt_mb(apps_size))}"
            if resolution.apps
            else dim("nenhum"),
        )
    )
    print(_row("pacotes", str(len(resolution.packages))))
    print(_row("iso", fmt_mb(resolution.iso_mb)))
    print(_row("download", blue(fmt_mb(resolution.download_mb))))
    print(_row("no disco", fmt_mb(resolution.disk_mb)))

    for warning in plan.warnings:
        print(f"  {yellow('!')} {dim(warning)}")
    print()


# ---------------------------------------------------------------------- comandos

def cmd_init(args: argparse.Namespace) -> int:
    catalog = Catalog.locate()
    base = catalog.base(args.base)

    graphical = {item.id: item for item in catalog.graphical_for(base.id)}
    if args.desktop not in graphical:
        raise CatalogError(
            f"desktop '{args.desktop}' indisponível em {base.label} "
            f"(disponíveis: {', '.join(graphical)})"
        )

    if args.apps:
        apps = [app.strip() for app in args.apps.split(",") if app.strip()]
    else:
        apps = catalog.default_apps(base.id)

    profile = Profile(
        name=args.name,
        version=args.version_name,
        base=base.id,
        variant=args.variant or base.build_codename,
        arch=args.arch,
        install_mode=args.install_mode,
        desktop=args.desktop,
        apps=apps,
    )

    out = Path(args.out)
    if out.exists() and not args.force:
        raise FileExistsError(f"{out} já existe; use --force para sobrescrever")
    profile.save(out)

    print(f"{green('✓')} perfil criado em {bold(str(out))}")
    print(_row("base", base.label))
    print(_row("desktop", graphical[profile.desktop].label))
    print(_row("apps", str(len(profile.apps))))
    print(dim("\n  próximo passo: distroforge plan " + str(out)))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    profile = Profile.from_file(args.file)
    catalog = Catalog.locate()
    resolution = catalog.resolve(profile)

    print(f"{green('✓')} perfil válido: {bold(profile.product_name)}")
    print(_row("base", resolution.base.label))
    print(_row("desktop", resolution.desktop.label))
    print(_row("pacotes", str(len(resolution.packages))))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    profile = Profile.from_file(args.file)
    orchestrator = Orchestrator(Catalog.locate())
    print_plan(orchestrator.plan(profile))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    profile = Profile.from_file(args.file)
    orchestrator = Orchestrator(Catalog.locate())
    generated = orchestrator.generate(profile, args.out, force=args.force)

    print(f"{green('✓')} árvore de build em {bold(str(generated.workdir))}")
    print(_row("arquivos", str(len(generated.files))))
    print(_row("overlay", str(generated.overlay)))
    print()
    for path in generated.files:
        try:
            shown = path.relative_to(generated.workdir)
        except ValueError:
            shown = path
        print(f"  {dim('·')} {shown}")
    print()
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    profile = Profile.from_file(args.file)
    orchestrator = Orchestrator(Catalog.locate())
    plan = orchestrator.plan(profile)
    print_plan(plan)

    result = orchestrator.build(
        profile,
        args.out,
        force=args.force,
        dry_run=args.dry_run,
    )

    if result.dry_run:
        print(f"{yellow('·')} dry-run: nenhum container foi iniciado")
        print("  " + " ".join(result.command))
        return 0

    print(f"{green('✓')} ISO gerada: {bold(str(result.iso))}")
    if result.log:
        print(_row("log", str(result.log)))
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import main as gui_main
    except ImportError:
        print(
            "erro: PySide6 não instalado; use pip install 'distroforge[gui]'",
            file=sys.stderr,
        )
        return 2
    return gui_main([])


def cmd_catalog(args: argparse.Namespace) -> int:
    catalog = Catalog.locate()
    print(f"\n  {bold('Catálogo')}  {dim(str(catalog.root))}\n")

    bases = [catalog.base(args.base)] if args.base else catalog.bases
    for base in bases:
        mark = green("●") if base.is_stable else dim("○")
        print(
            f"  {mark} {bold(base.label):<18} {dim(base.release):<18} "
            f"{dim(base.pkg_manager):<8} ISO ~{fmt_mb(base.iso_size)}"
        )
        if args.base:
            print()
            desktops = catalog.graphical_for(base.id)
            print(f"    {dim('desktops e WMs')}")
            for item in desktops:
                print(
                    f"    · {item.label:<16} {dim(fmt_mb(item.size_for(base.id))):<10} "
                    f"{dim(', '.join(item.packages(base.id)))}"
                )
            app_count = len(catalog.apps_for(base.id))
            print(f"\n    {dim(f'{app_count} apps disponíveis')}\n")
    print()
    return 0


# ------------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="distroforge",
        description="Construtor de distros Linux: perfil neutro, builders e instaladores.",
    )
    parser.add_argument("--version", action="version", version=f"distroforge {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="cria um profile.yaml a partir do catálogo")
    init.add_argument("--base", default="debian", choices=BASES)
    init.add_argument("--desktop", default="kde", help="id do desktop ou window manager")
    init.add_argument("--apps", help="lista separada por vírgula (padrão: recomendados)")
    init.add_argument("--name", default="MinhaDistro")
    init.add_argument("--version", dest="version_name", default="1.0")
    init.add_argument("--variant", default="", help="codinome da base (padrão: do catálogo)")
    init.add_argument("--arch", default="amd64", choices=ARCHES)
    init.add_argument("--install-mode", default="netinstall", choices=INSTALL_MODES)
    init.add_argument("--out", default="profile.yaml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    validate = subparsers.add_parser("validate", help="valida um perfil")
    validate.add_argument("file")
    validate.set_defaults(func=cmd_validate)

    plan = subparsers.add_parser("plan", help="mostra o que será construído")
    plan.add_argument("file")
    plan.set_defaults(func=cmd_plan)

    generate = subparsers.add_parser(
        "generate", help="escreve a árvore de build sem compilar a ISO"
    )
    generate.add_argument("file")
    generate.add_argument("--out", default="build")
    generate.add_argument("--force", action="store_true")
    generate.set_defaults(func=cmd_generate)

    build = subparsers.add_parser("build", help="gera a árvore e constrói a ISO")
    build.add_argument("file")
    build.add_argument("--out", default="out")
    build.add_argument("--force", action="store_true")
    build.add_argument("--dry-run", action="store_true", help="só mostra o comando")
    build.set_defaults(func=cmd_build)

    gui = subparsers.add_parser("gui", help="abre a interface gráfica")
    gui.set_defaults(func=cmd_gui)

    catalog = subparsers.add_parser("catalog", help="lista bases, desktops e apps")
    catalog.add_argument("--base", help="detalha uma base")
    catalog.set_defaults(func=cmd_catalog)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args) or 0)
    except (ProfileError, CatalogError, FileExistsError, ContainerError) as error:
        print(f"{_color('31', 'erro:')} {error}", file=sys.stderr)
        return 2
    except BuildError as error:
        print(f"{_color('31', 'falhou:')} {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompido", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
