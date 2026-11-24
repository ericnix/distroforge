# Fase 0 — PoC do instalador

Objetivo: provar que uma ISO mínima gerada pelo DistroForge boota, sobe o
Calamares e instala o sistema baixando os pacotes do repositório da base.

> Status: **instalação em validação**. Boot, live-config, Calamares e todas as
> telas até o netinstall já foram exercitados no QEMU; falta confirmar o fim da
> instalação e o primeiro boot do sistema no disco.

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
| Calamares abre | janela com branding, idioma e botões de suporte |
| Partições | detecta `/dev/vda` (20 GiB) e oferece "apagar disco" |
| Usuário | cria conta, valida senha |
| Desktop | packagechooser lista os 10 desktops/WMs da base Debian |
| Programas | netinstall com grupos, tamanhos e apps pré-marcados |
| Instalação | **em validação** (unpackfs + apt + bootloader) |

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
6. **`modules-search` quebrava o Calamares.** A lista declarada substitui o
   caminho compilado; no Debian multiarch os módulos ficam em
   `/usr/lib/x86_64-linux-gnu/calamares/modules`, então a nossa lista apontava
   para um diretório inexistente e nenhum módulo era carregado.
7. **`slideshow` é obrigatório no branding 3.3.** Sem a chave, o Calamares
   aborta com `FATAL` no `branding.desc`. O build copia o `show.qml` do tema
   padrão.
8. **Schema do `packagechooser`.** Os itens vão em `items` (não `labels`), e
   `mode`/`method` são obrigatórios. Com `method: packages` a escolha é
   entregue ao módulo `packages`.
9. **Schema do `netinstall`.** Grupos usam `subgroups`; `groupsUrl` precisa ser
   `file:///...`; grupos de topo defaultam para `selected: true`, o que
   instalaria o catálogo inteiro — agora vêm com `selected: false`.
10. **`grub-pc` e `grub-efi-amd64` são mutuamente exclusivos.** O rootfs usa os
    `*-bin` (BIOS, UEFI e assinado) para o Calamares instalar em qualquer
    firmware.
11. **`modules-search` ausente = lista vazia.** O Calamares não usa um default:
    `interpretModulesSearch` devolve vazio quando a chave não existe. O valor
    correto é `[ local ]`, que resolve para `<libdir>/calamares/modules`
    (multiarch no Debian).
12. **O pacote `calamares` não traz nenhum `.conf` de módulo.** Quem fornece
    `users`, `bootloader`, `packages`, `welcome`, `unpackfs` etc. é o
    `calamares-settings-debian`; sem ele o instalador não tem como particionar
    nem criar usuário.

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
