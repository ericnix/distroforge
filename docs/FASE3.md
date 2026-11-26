# Fase 3 — Arch Linux e Ubuntu

> Status: **Ubuntu validado** — ISO de 1,4 GB boota, autologin funciona,
> Calamares abre com o branding e a tela de partições reconhece o disco.
> **Arch**: ISO gerada, `switch-root` OK; boot travava no `systemd-firstboot`
> (corrigido, reconstrução em curso).

## Arch Linux

O plano assumia "Arch usa Calamares como o EndeavourOS". Na prática, o
`calamares` **saiu dos repositórios oficiais** do Arch e vive só no AUR
(3.4.2). O builder precisou de um pipeline próprio.

### Pipeline do calamares (AUR → repositório local)

1. `makepkg` compila o pacote do AUR como usuário `builder` (makepkg não roda
   como root).
2. O `.pkg.tar.zst` é copiado para `~/.cache/distroforge/aur/` (cache entre
   builds).
3. Um repositório local é montado em `/build/localrepo` com `repo-add`.
4. O `pacman.conf` do perfil aponta para `file:///build/localrepo`, então o
   `mkarchiso` consegue instalar `calamares` no airootfs.

### Ajustes que o archiso exige

| Item | Motivo |
|---|---|
| `syslinux/syslinux.cfg` e `efiboot/loader/entries/*.conf` | `mkarchiso` valida o perfil e aborta sem eles |
| `syslinux` em `packages.x86_64` | boot BIOS |
| `etc/mkinitcpio.conf` com hook `archiso` | sem ele o initramfs não monta a mídia e cai em *emergency mode* |
| `NetworkManager.service` habilitado | netinstall sem rede falha |
| serviço `distroforge-live.service` | prepara autologin/sessão só quando `/run/archiso` existe |

### Podman rootless

`mkarchiso` usa `pacstrap`/`arch-chroot`, que montam `devtmpfs` e `sysfs`. Em
user namespace isso dá `permission denied`. O build aplica um patch de texto
nesses dois scripts, trocando:

- `mount -t devtmpfs` → `mount --bind /dev`
- `mount -t sysfs` → `mount --bind /sys`
- `devpts`/`shm` → no-op (já vêm do bind)

Detalhe: `--rbind` deixa submounts presos e o cleanup do `mkarchiso` bate em
*I/O error*; o bind simples resolve.

### Sessão live

`archiso` autologa como **root**, então o instalador sobe sem sudo:

```
ConditionPathExists=/run/archiso
→ distroforge-live-setup (getty autologin root + profile.d/xinit)
```

O serviço existe no sistema instalado, mas a condição impede que rode fora do
live.

## Ubuntu

O Ubuntu usa o mesmo `live-build` do Debian, com ajustes:

```bash
lb config --mode ubuntu --distribution noble \
  --mirror-bootstrap http://archive.ubuntu.com/ubuntu/ \
  --mirror-chroot    http://archive.ubuntu.com/ubuntu/
```

- componentes: `main restricted universe multiverse`
- firmware: `linux-firmware` (não os pacotes `firmware-*` do Debian)
- `ubuntu-keyring` no container de build
- `calamares-settings-debian` existe no universo do Ubuntu, então a lista de
  pacotes do live é a mesma
- kernel: `--linux-packages "linux-image linux-headers" --linux-flavours generic`
- `--apt-recommends false` (dictionaries-common quebra o postinst no chroot)

### Workarounds de container (user namespace)

| Problema | Workaround |
|---|---|
| `apt-key` não escreve em `/dev/null` (arquivo comum, `mknod` proibido) | wrapper do `debootstrap` faz bind do `/dev/null` real |
| `gpgv`/`gpg` ausentes no minbase | `--debootstrap-options "--include=gpgv,gnupg"` |
| verificação de assinatura falha mesmo assim | `--apt-secure false` no build; `sources.list` limpo é sobrescrito no overlay |
| `dictionaries-common` falha no postinst | `--apt-recommends false` |

### Causa raiz de todas as falhas de rede: placa não gerenciada

O `network-manager` do Ubuntu traz
`/usr/lib/NetworkManager/conf.d/10-globally-managed-devices.conf`:

```
[keyfile]
unmanaged-devices=*,except:type:wifi,except:type:gsm,except:type:cdma
```

Resultado: a placa ethernet (`ens3`) fica **DOWN e "unmanaged"**, a live não
tem rede e o `apt` do sistema instalado falha com
`Temporary failure resolving 'archive.ubuntu.com'` (1095 falhas no log).
O Debian não tem esse arquivo, por isso funcionava. O overlay sobrescreve com
`unmanaged-devices=` (gerencia tudo).

### Descobertas do live Ubuntu

- `sfdisk` não vem no `util-linux` do Ubuntu: está no pacote **`fdisk`**, e o
  backend `pmsfdiskbackendplugin` do Calamares depende dele. Sem `fdisk` o
  instalador mostra "There are no partitions to install on" mesmo com disco.
- o `initrd.img` do live não incluía `virtio_blk`/`ata_piix` (só `ahci`),
  mesmo com `MODULES=most`. Correção: `/etc/initramfs-tools/modules` no overlay
  com `virtio*`, `ata_piix`, `ahci` e `sd_mod`; o rebuild do live-build roda
  depois dos includes, então os módulos entram. Disco virtio (`/dev/vda`)
  passa a ser detectado.
- `libpwquality` precisa do dicionário do **`cracklib-runtime`**; sem ele a
  tela de usuário mostra "error loading dictionary" e o Next fica bloqueado.
- **`partition.conf` explícito**: o pacote `calamares` e o
  `calamares-settings-debian` não trazem nenhum `.conf` de módulo de
  particionamento. Com os defaults do binário, o Ubuntu gerou **só swap**
  (13,6 GiB como "Free Space", sem partição raiz) e o `unpackfs` falhou com
  `rsync failed with error code 11`. O adapter agora grava
  `defaultFileSystemType: ext4`, `initialSwapChoice: none` e um
  `partitionLayout` explícito com uma única partição raiz (`100%`, ext4).

  Confirmado no Summary: `After: rootfs 19,99 GiB ext4` + GRUB no MBR,
  igual ao comportamento do Debian.
- **`packages.conf` por base**: a lista de remoção herdada do
  `calamares-settings-debian` trazia `live-task-localisation` e
  `live-task-recommended`, que não existem no Ubuntu — o `apt-get remove`
  retornava 100 e o módulo parava **antes** de instalar os programas do
  netinstall. O adapter agora gera o `packages.conf` por base.

### Sessão errada no SDDM: tela preta após o login

Depois de a instalação chegar a 100%, o sistema instalava, boota no SDDM e o
login caía em **tela preta com cursor**. O `state.conf` do SDDM mostrava
`Session=/usr/share/xsessions/openbox.desktop`.

Causa: o live é montado com o pacote `openbox` para "dar uma sessão gráfica ao
Calamares", mas na prática o live sobe com
`xinit /usr/local/bin/distroforge-session` — um script que só executa o
`calamares`. **Ninguém inicia o window manager.** O pacote só servia para
embarcar `openbox.desktop` no squashfs, que o `unpackfs` copiava para o sistema
instalado junto com o `plasma.desktop` do netinstall.

Com duas sessões, o SDDM escolhe a primeira em ordem alfabética:
**Openbox < Plasma** → `openbox-session` sem configuração nenhuma → tela preta.

Correção: `openbox` saiu de `LIVE_PACKAGES` (commit `d286d0b`). Quem quiser
openbox como desktop escolhe no `packagechooser` e o `netinstall` o instala no
alvo, onde ele é a única sessão.

Diagnóstico útil: `journalctl -b -u sddm` mostra
`Session "/usr/share/xsessions/….desktop" selected, command: "…"`, e
`/var/lib/sddm/state.conf` guarda a última sessão usada.

### Pendência do initramfs

A ISO boota, o `user-setup` cria o usuário e o Calamares abre com o branding.
Mas o instalador não enxerga nenhum disco: o `initrd.img` do live foi gerado em
modo **`dep`** (só o hardware do container, `ahci`), sem `virtio_blk` nem
`ata_piix`.

Correção proposta: um hook `*.hook.chroot` que force
`MODULES=most` em `/etc/initramfs-tools/initramfs.conf` e rode
`update-initramfs -u -k all` **depois** dos includes e antes do empacotamento.

### Causa do `sources.list` vazio (confirmada)

No fim do build, `lb chroot_archives remove` executa
`Create_apt_sources_list binary`, que usa **`LB_MIRROR_BINARY`**. Como só
passávamos `--mirror-bootstrap` e `--mirror-chroot`, a variável ficava vazia e o
arquivo saía como `deb  noble main restricted universe multiverse` — o apt
abortava com "Malformed entry 1".

Correção: passar também `--mirror-binary`, `--mirror-binary-security` e os
equivalentes `--parent-mirror-binary*`.

## Como reproduzir

```bash
distroforge init --base arch --desktop kde --apps firefox,git \
  --name "Minha Distro Arch" --out arch.yaml
distroforge build arch.yaml --out out
python3 scripts/qemu-install-test.py out/minha-distro-arch-1.0-amd64.iso
```

O primeiro build compila o Calamares do AUR (~10 min); os seguintes usam o cache.

## Pendência: boot do Arch

O `switch-root` **funciona** — o initramfs monta `/dev/sr0` e o airootfs, e o
sistema chega ao live. O boot então parava num outro ponto: o
`systemd-firstboot` (ordenado antes de `sysinit.target`) ficava em tty pedindo
timezone, porque o airootfs não tinha os arquivos que o releng do archiso traz:

- `/etc/localtime` → symlink para `/usr/share/zoneinfo/UTC` (sem ele, pergunta o timezone)
- `/etc/locale.conf` (`LANG=C.UTF-8`) (sem ele, pergunta o locale)
- `/etc/hostname` (sem ele, pergunta o hostname)
- `/etc/shadow` com `root::` — campo de senha **vazio**, não `!`; root travado
  faz o firstboot perguntar a senha do root

Correção no commit `9a2191c`. Como o `archiso` monta o prompt no console
(`console=ttyS0`), o sintoma era um shell parado no serial, não uma mensagem de
erro — fácil de confundir com falha de switch-root.

Próximos passos: bootar a ISO reconstruída e validar o instalador de ponta a
ponta. Controle útil: a ISO oficial do Arch no mesmo QEMU, para isolar
ambiente × perfil.

Já verificado:

- UUID do ISO (`blkid`) bate com `archisosearchuuid` no menu
- `/boot/<uuid>.uuid` existe na ISO
- `/arch/x86_64/airootfs.sfs` existe
- o initramfs contém `hooks/archiso` (build log confirma todos os hooks)
- `mkinitcpio-archiso` (não `archiso`) é o pacote que fornece os hooks
