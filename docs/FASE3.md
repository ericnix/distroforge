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

## Validação do Ubuntu (fase 1 completa)

Ciclo completo automatizado, do build ao desktop:

1. `distroforge build ubu.yaml` → ISO de 1,4 GB;
2. wizard do Calamares via VNC (`/tmp/ubu-full.py`) → instalação a **100% "Done"**;
3. boot do disco instalado → **SDDM** com o usuário criado;
4. login → **KDE Plasma** no ar (painel, relógio, wallpaper).

Evidências em `df-poc/vm/ubu-verify/` (`01-boot` … `11-desktop`) e o disco em
`df-poc/vm/ubu-full.qcow2` (4,5 GB).

Bugs encontrados e corrigidos nesse ciclo (cada um com teste):

| Commit | Bug |
|---|---|
| `3b95279` | sem `partitionLayout` o Ubuntu gerava só swap, sem raiz |
| `54669c2` | `packages.conf` trazia `live-task-*`, inexistente no Ubuntu |
| `faac04d` | `resolv.conf` era symlink do stub do `resolved` (127.0.0.53) |
| `605274f` | `nsswitch` com `resolve [!UNAVAIL=return]` bloqueava o DNS |
| `d413875` | `networkcfg` regravava o `resolv.conf` por cima do overlay |
| `5930fb4` | `network-manager` marcava a placa ethernet como *unmanaged* |
| `d286d0b` | `openbox` no live vazava `openbox.desktop` → SDDM escolhia Openbox |

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

### Cadeia de bugs do live Arch (todos corrigidos)

Depois do firstboot, cada camada revelou o próximo problema. O sintoma final
era sempre "tela preta", então o diagnóstico foi serial interativo
(`-serial tcp:...` + `systemctl status`):

| Commit | Bug | Evidência |
|---|---|---|
| `9a2191c` | faltavam `hostname`/`locale.conf`/`localtime`/`shadow` | `systemd-firstboot` parado pedindo timezone |
| `c1d6926` | `openbox` no live vazava `openbox.desktop` | SDDM escolhia Openbox → tela preta |
| `46e77ae` | script de live sem bit de execução | `status=203/EXEC` na unit |
| `42996ae` | drop-in do `getty@tty1` sem `daemon-reload` | agetty padrão no tty1, `startx` nunca rodava |
| `a652e87` | `python` ausente no `packages.x86_64` | `libpython3.14.so.1.0 => not found`, Xorg saía com 0 |

### O Calamares do AUR não é o do Debian

Com a fonte no lugar, o instalador subiu — e mostrou **tela cheia de
"Calamares Initialization Failed"** listando três módulos:
`packagechooser`, `initramfscfg` e `initramfs`. O `settings.conf` que
gerávamos valia para o Debian e não para o Arch:

| O que o Debian tem | O que o AUR tem |
|---|---|
| `packagechooser` (escolhe o desktop) | **não existe** |
| `initramfscfg` / `initramfs` | `initcpiocfg` / `initcpio` |

Três problemas em cascata, todos invisíveis até a fonte corrigir a tela:

1. **A sequência abortava** — o Calamares lista os módulos que não achou e
   a UI fica inutilizável. Corrigido com `MODULE_ALIASES`/`MISSING_MODULES`
   por base em `calamares.py`.
2. **Sem `packagechooser`, ninguém instalava o desktop.** No Debian é ele
   que entrega `task-kde-desktop`; no Arch a escolha passou para o
   **netinstall**, que ganhou o grupo "Ambiente gráfico" com os itens de
   `graphical_for()` pré-marcados pelo `desktop` do perfil.
3. **Sem `packages.conf`, o módulo caía no default `backend: dummy`.** O
   dummy só escreve no log: o netinstall escolheria os pacotes e *nada*
   seria instalado — nem desktop, nem apps. Além disso o alvo sai do
   squashfs **sem `/var/lib/pacman/sync`**, então o `update_db: true`
   (um `pacman -Sy`) é obrigatório senão o `pacman -S` falha com
   *"target not found"*.

E um quarto, só aparece depois de tudo instalado: no Arch o preset do
systemd é `disable *` e **o `displaymanager` do Calamares só configura
autologin — ele não habilita a unit**. No Debian/Ubuntu o postinst do
`sddm` faz isso sozinho; no Arch o sistema instalado subiria no getty,
sem tela de login. Resolvido com `services-systemd.conf` listando as units
candidatas (`plasmalogin`, `sddm`, `gdm`, `lightdm`) — o módulo suprime
silenciosamente as que não existirem.

Nota de diagnóstico: o `plasma-meta` do Arch não puxa `sddm`, mas puxa
`plasma-login-manager` (o `/usr/bin/plasmalogin`), e o
`displaymanager.conf` do próprio pacote AUR já o lista — por isso a
candidata correta é `plasmalogin.service`.

### Uma URL só na checagem de rede é ponto único de falha

Com a rede no ar e o `nm-online` antes do `xinit`, a página **continuava**
marcando *"not connected to the Internet"*. A causa: a `welcome.conf` do
AUR traz `internetCheckUrl: http://example.com` — **uma URL só**, e neste
ambiente `example.com` simplesmente não resolve:

```
$ getent hosts example.com      →  (nada)
$ curl -sI http://example.com   →  rc=000 em 88 ms
$ curl -sI https://archlinux.org →  HTTP/2 200
```

O `welcome` marca `hasInternet=false` para sempre, e é `hasInternet` que
libera o `update_db` (`pacman -Sy`) do módulo `packages`. Sem o `-Sy` o
`pacman -S` do alvo falha com *"target not found"* — o squashfs sai sem
`/var/lib/pacman/sync`. Ou seja: **um domínio fora do ar derrubaria a
instalação inteira**, não só exibiria um aviso.

Correção: geramos a `welcome.conf` nas bases pacman com `internetCheckUrl`
como **lista** (`distroforge-site.pages.dev`, `archlinux.org`,
`example.org`). O próprio Calamares documenta o recurso: as URLs são
testadas em sequência e basta **uma** responder.

O Debian/Ubuntu não tem o problema porque o `calamares-settings-debian`
sequer inclui `internet` na lista `check`.

### Três barreiras entre o `users` e o `bootloader`

Com o `sudo` e as fontes resolvidos, a instalação avançou até o job
`packages` — e morreu em *"Package Manager error"*. Cada uma das três
causas seguintes só se manifesta no **alvo**, nunca no build, e cada uma
foi confirmada com um teste no chroot do disco que falhou.

**1. Mirrorlist sem nenhum servidor ativo.** O `pacman-mirrorlist`
(20260610) vem com **todos os 425 servidores comentados** — quem instala
é esperado escrever o próprio (o `archinstall` faz; o mkarchiso não toca
no arquivo). O erro era `no servers configured for repository`.

Um teste A/B me corrigiu: escrevi o `resolv.conf` com nameservers e
rodar o `pacman -Sy` de novo **continuou falhando igual** — o problema
não era DNS. Só olhar o mirrorlist (0 linhas `^Server`) revelou a causa.
O build não cai nisso porque o `Include` resolve no **container**, cuja
mirrorlist da imagem tem servidores ativos; o alvo recebe a do pacote.

**2. `resolv.conf` sem nenhum nameserver.** O squashfs traz o default do
sistema — só comentários. No live o NetworkManager reescreve em runtime,
mas o alvo recebe o do squashfs, e o Calamares **não copia** o do host
(confirmedo: `libcalamares.so` não tem nenhuma string `resolv`). É a
mesma correção que já aplicávamos no Debian/Ubuntu.

**3. `/boot` vazio no alvo.** O mkarchiso apaga **todo** o `/boot` do
airootfs antes de gerar o squashfs:

```bash
# Delete all files in /boot
[[ -d "${pacstrap_dir}/boot" ]] && find "${pacstrap_dir}/boot" -mindepth 1 -delete
```

O kernel vai só para a ISO (`arch/boot/x86_64/`). Como o alvo nasce do
`unpackfs`, ele chega **sem `/boot/vmlinuz-linux`**. Testado no alvo:

```
$ mkinitcpio -P
==> ERROR: Invalid option -k -- '/boot/vmlinuz-linux' must be readable
$ ls /usr/lib/modules/*/vmlinuz
/usr/lib/modules/7.3.6-arch1-1/vmlinuz      ← o kernel está aqui
```

O preset (`ALL_kver="/boot/vmlinuz-linux"`) e o `grub-mkconfig` (que
procura `/boot/vmlinuz-*` para gerar a entrada de boot) dependem do
arquivo. Um `shellprocess` o copia de `/usr/lib/modules` antes de
`initcpiocfg`.

Detalhe que custaria uma hora: o expander do `shellprocess` usa `$` como
**símbolo de macro** (`StringExpander`: *"`$` as macro-symbol"*), então
qualquer `$var` no script viraria "variável não definida" e abortaria o
job. O comando foi escrito sem nenhum `$`.

**Lições** — o padrão se repete três vezes:

- **Testes A/B no alvo real valem mais que leitura de código.** O teste
  do `resolv.conf` *refutou* minha própria hipótese e apontou para o
  mirrorlist; sem ele eu teria commitado uma correção que não resolvia.
- **O build validar nada não significa que o alvo valide.** O `Include`
  resolve no container e o `unpackfs` copia o squashfs — os dois caminhos
  de leitura do `pacman.conf` são diferentes.
- **`/boot` vazio é invisível até o mkinitcpio.** Nenhum teste de
  geração pega isso; só rodar o instalador até o fim.

### A rede tinha que estar no ar antes do X

Com a fonte e os módulos certos, a página de boas-vindas apareceu com
*"The system is not connected to the Internet"*. A rede **funcionava** —
`nmcli` reportava `full`, DNS resolvia, `ens3` com `10.0.2.15` — só que a
checagem do `welcome` roda **uma única vez** ao carregar a página e grava
`hasInternet` no global storage. O X subia junto com o getty, antes do
NetworkManager terminar de configurar a placa, e a marcação ficava
`false` para sempre.

Isso não é cosmético: é `hasInternet` que libera o `update_db`
(`pacman -Sy`) do módulo `packages`. Sem ele, o `pacman -S` do alvo falha
com *"target not found"* — o squashfs sai sem `/var/lib/pacman/sync`.

Correção no `distroforge-live-setup`: `nm-online -q --timeout=30` antes
do `xinit`. Sem `-s`, que só esperaria o *startup* do NM (o estado
`CONNECTED_SITE`); a checagem HTTP do welcome precisa da conectividade
plena (`CONNECTED_GLOBAL`), que o journal mostrou chegando 3 s depois.
Com timeout e `||` o instalador segue mesmo sem rede, para não travar o
live numa máquina sem cabo.

Dois detalhes que custaram tempo:

- **`file_permissions` do `profiledef.sh` é obrigatório.** O mkarchiso copia o
  airootfs com `cp -af --no-preserve=ownership,mode` — os bits de execução do
  profile são descartados de propósito e só a lista do `profiledef.sh` os
  re-aplica.
- **`daemon-reload` antes do getty.** O systemd constrói a transação de boot e
  carrega `getty@tty1` antes do nosso script escrever o drop-in; sem recarregar
  ele ignora o arquivo (e até avisa: *"drop-ins changed on disk"*).

O `calamares` do AUR linka `libpython` (os módulos `bootloader`,
`displaymanager` e `fstab` são Python), mas o PKGBUILD não declara `python`
como dependência — o `pacman` não puxa nada e o binário morre em `ldd`.

### Causa raiz do "display não inicializado": fontes ausentes

O sintoma era o QEMU exibindo *Guest has not initialized the display (yet)*,
o `fb0` em `blank=4` e o `crtc-0 active=0`, com o `calamares` e o `Xorg`
vivos no serial. Diagnóstico longo e **enganado por completo**: testei
`MODULES=(bochs)` no initramfs, troquei `-vga std` por `cirrus` e `bochs-display`,
escrevi lixo em `/dev/fb0` e em `0xb8000`, desliguei o blank à mão — nada
mudou, porque o problema não era de vídeo.

A pista certa estava na cor das capturas. O placeholder do QEMU é preto
(96,6% dos pixels) com texto cinza-claro; as capturas do Arch tinham 84%
de `#efefef` e 11% de `#0b0f1a` — **a UI do Calamares estava sendo
renderizada o tempo todo**. O texto, porém, saía inteiro em caixas vazias
(*tofu*): o Qt não achava nenhuma TTF e caía no glifo `.notdef`.

O Xorg já avisava no log, e foi ignorado como ruído:

```
(WW) The directory "/usr/share/fonts/TTF" does not exist.
(WW) The directory "/usr/share/fonts/misc" does not exist.
```

Causa: a `PACKAGES` do Arch não tinha `fontconfig` nem nenhuma fonte. O
Debian/Ubuntu funcionava porque `fonts-dejavu-core` entra por dependência
(`calamares-settings-debian`/`xfonts-base`) — nada lá é declarado de
propósito, o que por si só já era uma bomba de tempo.

Correção: `fontconfig` + `ttf-dejavu` em `PACKAGES`, com teste de
regressão (`test_arch_traz_uma_fonte_para_o_calamares`). Como o Arch usa
`unpackfs` (copia o squashfs inteiro), a correção vale para o live **e**
para o sistema instalado.

**Lições** — duas, e a primeira custou horas:

1. **Diferenciar "tela preta" de "UI sem texto".** Medir a distribuição de
   cores da captura (ou ler a imagem) decide em segundos se o display está
   morto ou se é outro subsistema. O placeholder do QEMU tem assinatura
   própria: preto dominante + cinza `#aaaaaa`.
2. **`blank=4` e `crtc active=0` são sintoma, não causa.** Ambos são o
   estado normal de um fbcon desativado enquanto o Xorg é o master do DRM —
   o Ubuntu no mesmo QEMU mostra exatamente o mesmo estado e funciona.

Também ficou em teste `MODULES=(bochs)` no `mkinitcpio.conf` (o initramfs
padrão do Arch tem `MODULES=()` e o driver de vídeo só carrega depois do
switch-root). É inofensivo e dá framebuffer desde o initramfs, mas **não**
era o remédio para este bug.

Próximos passos: bootar a ISO reconstruída e validar o instalador de ponta a
ponta. Controle útil: a ISO oficial do Arch no mesmo QEMU, para isolar
ambiente × perfil.

Já verificado:

- UUID do ISO (`blkid`) bate com `archisosearchuuid` no menu
- `/boot/<uuid>.uuid` existe na ISO
- `/arch/x86_64/airootfs.sfs` existe
- o initramfs contém `hooks/archiso` (build log confirma todos os hooks)
- `mkinitcpio-archiso` (não `archiso`) é o pacote que fornece os hooks
