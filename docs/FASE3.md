# Fase 3 — Arch Linux e Ubuntu

> Status: **build do Arch ok** (ISO de ~1 GB gerada). Boot e instalador em
> validação. Ubuntu: geração de árvore pronta, build ainda não exercitado.

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

## Como reproduzir

```bash
distroforge init --base arch --desktop kde --apps firefox,git \
  --name "Minha Distro Arch" --out arch.yaml
distroforge build arch.yaml --out out
python3 scripts/qemu-install-test.py out/minha-distro-arch-1.0-amd64.iso
```

O primeiro build compila o Calamares do AUR (~10 min); os seguintes usam o cache.
