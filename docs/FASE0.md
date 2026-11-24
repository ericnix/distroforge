# Fase 0 — PoC do instalador

Objetivo: provar que uma ISO mínima gerada pelo DistroForge boota, sobe o
Calamares e instala o sistema baixando os pacotes do repositório da base.

> Status: **em validação**. O boot e o live-config já foram confirmados; falta
> confirmar o autostart do Calamares na última ISO (correções aplicadas).

## Perfil usado

```yaml
meta:
  name: Minha Distro
  version: "1.0"
  hostname: minha-distro
base: debian
variant: trixie
arch: amd64
install_mode: netinstall
desktop_default: kde
apps_default: [firefox, libreoffice, vlc, git]
```

Comando:

```bash
distroforge build profile.yaml --out out
```

## O que já foi confirmado

| Etapa | Resultado |
|---|---|
| `debian:trixie-slim` no podman rootless | ok |
| `lb config` + `lb build` no container | ok, ~10 min |
| ISO híbrida gerada | 1,1 GB, `isolinux` + `/efi.img` |
| Boot BIOS no QEMU | chega ao menu do isolinux |
| Kernel + initramfs | Linux 6.12.118, boota |
| live-config | cria usuário e faz autologin na tty1 |
| Sessão gráfica + Calamares | **em validação** |

## Correções encontradas no caminho

1. **Menu esperava Enter para sempre.** O runtime do live-build não tem
   `--bootloader-timeout`; o template gera `timeout 0`. A correção é sobrescrever
   `config/bootloaders/isolinux/isolinux.cfg` com `timeout 50` (5 s).
2. **`startx` não rodava.** O gatilho ficava em `.bash_profile` e o shell do
   usuário live não é necessariamente bash. Agora fica em
   `/etc/profile.d/zz-distroforge-startx.sh`, que vale para bash, dash e zsh.
3. **Calamares exige root.** O live-config pode não deixar sudo sem senha.
   O build agora instala `/etc/sudoers.d/90-distroforge` com `NOPASSWD` e
   `env_keep` de `DISPLAY`/`XAUTHORITY`, e sobe via
   `xinit /usr/local/bin/distroforge-session` (`sudo -E calamares`).
4. **`--force` não conseguia limpar a árvore antiga.** Em podman rootless,
   processos não-root do container gravam com subuids. `remove_tree()` tenta
   `shutil.rmtree` e, no `PermissionError`, remove de dentro do container.
5. **Rótulo do volume com hífen.** ISO 9660 só aceita `A-Z0-9_`;
   `iso_volume_label()` normaliza o nome.

## Como repetir o teste

```bash
# build (~10 min)
distroforge build profile.yaml --out out --force

# boot headless com capturas de tela
python3 scripts/qemu-test.py out/minha-distro-1.0-amd64.iso
```

As telas saem em `shots/boot*.png` e o console serial em `shots/serial.log`.

## Riscos ainda abertos

- X no QEMU (`-vga std`) depende do driver `modesetting`; em hardware real pode
  precisar de firmware adicional.
- O `unpackfs` do Calamares aponta para `/run/live/medium/live/filesystem.squashfs`;
  o caminho muda entre versões do live-boot e precisa ser confirmado na instalação.
- O menu de boot ainda mostra o título padrão do Debian (branding do isolinux).
- Instalação em si (particionar, gravar GRUB, baixar KDE) ainda não foi exercitada
  de ponta a ponta.
