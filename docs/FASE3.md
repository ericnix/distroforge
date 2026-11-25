# Fase 3 — Arch Linux e Ubuntu

> Status: **Arch**: ISO gerada, boot live para no `switch_root`.
> **Ubuntu**: build avança até o fim dos pacotes, mas quebra na limpeza do
> `live-build` (sources.list malformado). Ambos documentados abaixo.

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

A ISO boota (syslinux → kernel → initrd), mas o systemd do initramfs falha em
`systemd-switch-root.service` e cai em *emergency mode*.

Já verificado:

- UUID do ISO (`blkid`) bate com `archisosearchuuid` no menu
- `/boot/<uuid>.uuid` existe na ISO
- `/arch/x86_64/airootfs.sfs` existe
- o initramfs contém `hooks/archiso` (build log confirma todos os hooks)
- `mkinitcpio-archiso` (não `archiso`) é o pacote que fornece os hooks

Hipótese principal: no mkinitcpio 42 o initramfs roda systemd como init e o
`mount_handler` exportado pelo hook `archiso` (pensado para o init do
initcpio) não é invocado. Próximos passos sugeridos:

1. bootar a ISO oficial do Arch no mesmo QEMU como controle (isolar se é
   ambiente ou perfil);
2. testar `archisodevice=/dev/sr0` explícito no `APPEND`;
3. comparar o initramfs gerado com o da ISO oficial (`lsinitcpio`).
