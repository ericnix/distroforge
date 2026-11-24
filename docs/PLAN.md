# DistroForge — Construtor de distros Linux com GUI

> Plano de projeto. Status: **planejamento** (nenhum código escrito ainda).
> Autor: sessão de planejamento · Data: 2026-11-23

---

## 1. Visão

Um programa desktop com GUI que monta ISOs Linux **netinstall** customizadas:

1. Você escolhe a **base** (Debian, Ubuntu, Arch; depois Fedora e openSUSE).
2. Você define **branding** (nome, logo, wallpaper, cor, hostname).
3. Você escolhe o **catálogo padrão** de desktops/WMs e programas.
4. O programa gera uma **ISO live com instalador**, onde o usuário final ainda pode
   trocar desktop e programas na hora de instalar.
5. A ISO instala baixando os pacotes dos **repos da própria base** — sem repo próprio,
   sem infraestrutura de updates.

O sistema instalado atualiza direto de Debian/Ubuntu/Arch/Fedora/openSUSE.
Isso é **remaster com netinstall**, não uma distro independente.

---

## 2. Decisões fechadas

| Decisão | Escolha | Motivo |
|---|---|---|
| Modelo de instalação | **Netinstall por base** (Modelo B) | ISO ~900 MB, desktop/apps escolhidos na instalação |
| Bases no MVP | **Debian + Ubuntu + Arch** | As três usam Calamares de verdade |
| Fedora / openSUSE | Fase posterior, **ISOs próprias** | Anaconda (kickstart + addon) e Agama (perfil JSON) |
| GUI | **PySide6 / Qt6** | Nativo no host (Fedora KDE), já instalado |
| Escopo | **Remaster com repos da base** | Sem repo próprio, GPG e CI |
| Build | **Container podman** por base | Host limpo; loop devices e mounts isolados |

### Ambiente do host (verificado)

- Fedora 45 KDE, x86_64, 91 GB livres em `/home`
- `podman`, `docker`, `qemu-system-x86_64`, `python3`, `PySide6`, `PyGObject` disponíveis
- Internet OK (deb.debian.org, geo.mirror.pkgbuild.com)

---

## 3. Arquitetura

Duas dimensões independentes. Misturá-las é o que torna esses projetos ingovernáveis.

```
        ┌─────────────────────────────────────────┐
        │  PERFIL NEUTRO (YAML) — o contrato      │
        │  base, desktop, apps, branding, usuário │
        └───────────────┬─────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
┌───────────────────┐         ┌──────────────────────┐
│ BASE BUILDER      │         │ INSTALLER ADAPTER    │
│ monta o live ISO  │         │ traduz o perfil      │
├───────────────────┤         ├──────────────────────┤
│ live-build → deb  │         │ Calamares → deb/ubu  │
│ live-build → ubu  │         │ Calamares → arch     │
│ archiso    → arch │         │ Anaconda  → fedora   │
│ lorax      → fed  │         │ Agama     → opensuse │
│ kiwi       → suse │         │                      │
└───────────────────┘         └──────────────────────┘
```

**Adicionar uma base = um builder + um adapter.** Nada mais muda.

### Camadas

1. **`app/`** — GUI PySide6. Só conhece o perfil neutro, nunca detalhes de distro.
2. **`core/`** — perfil, catálogo, orquestrador. Sem I/O de distro específica.
3. **`builders/`** — como montar o live ISO (comandos dentro do container).
4. **`installers/`** — como apresentar as opções na instalação (gera configs).
5. **`catalog/`** — dados: capacidade → pacote por base. Fonte única de verdade.

---

## 4. Perfil neutro

```yaml
# profile.yaml — gerado pela GUI, consumido por qualquer backend
meta:
  name: "MinhaDistro"
  version: "1.0"
  hostname: "minhadistro"
base: debian                # debian | ubuntu | arch | fedora | opensuse
variant: trixie
arch: amd64
install_mode: netinstall    # netinstall | offline
desktop_default: kde
apps_default: [browser, office, media, dev]
branding:
  logo: assets/logo.svg
  wallpaper: assets/wall.jpg
  color: "#3b82f6"
offline_fallback: minimal   # perfil mínimo se a rede falhar
```

Validação com `pydantic`. O perfil é o único acoplamento entre GUI e backends.

---

## 5. Matriz de backends

| Base | Builder do live | Instalador | Mecanismo netinstall |
|---|---|---|---|
| Debian | `live-build` | Calamares | `netinstall` + `packagechooser` |
| Ubuntu | `live-build` | Calamares | idem |
| Arch | `archiso` | Calamares | idem (modelo EndeavourOS) |
| Fedora | `lorax` / `livemedia-creator` | Anaconda | kickstart `%packages` + addon |
| openSUSE | `kiwi` | Agama | perfil JSON |

---

## 6. Como cada instalador recebe as opções (sem fork)

### 6.1 Calamares (Debian / Ubuntu / Arch) — módulos stock, zero código novo

- `packagechooser.yaml` → tela "escolha seu desktop", com ícone e tamanho
- `netinstall.yaml` → grupos de apps com checkboxes
- `branding.desc` → nome, logo, cores, wallpaper

Sequência de módulos (validar ordem no PoC):

```yaml
# /etc/calamares/settings.conf (resumo)
modules-search: [ local, /usr/lib/calamares/modules ]

show:
  - welcome
  - locale
  - keyboard
  - partition
  - users
  - packagechooser
  - netinstall
  - summary
  - finished

exec:
  - partition
  - mount
  - unpackfs
  - machineid
  - fstab
  - locale
  - keyboard
  - localecfg
  - users
  - displaymanager
  - networkcfg
  - hwclock
  - services-systemd
  - packagechooser
  - netinstall
  - packages
  - bootloader
  - umount
```

`unpackfs` aponta para o squashfs do live:

```yaml
# modules/unpackfs.conf
unpack:
  - source: "/run/live/medium/live/filesystem.squashfs"
    sourcefs: "squashfs"
    destination: ""
```

> live-boot antigo usa `/lib/live/mount/medium/live/filesystem.squashfs`.
> Detectar os dois caminhos no PoC.

### 6.2 Anaconda (Fedora) — kickstart parcial, sem fork

Fork do Anaconda = manutenção eterna (muda a cada release). O caminho oficial:

```
# apenas as seções que você quer fixar; o resto o Anaconda pergunta
lang pt_BR.UTF-8
%packages
@kde-desktop
firefox
%end
```

O Anaconda em modo interativo **pergunta o que falta** (partição, usuário, rede).
Isso já imita ~80% do Calamares.

Telas próprias (grid de desktops com ícones) só se indispensável → **Anaconda addon**
(API Python oficial). Fase 6, e assumindo quebra a cada release.

### 6.3 Agama (openSUSE) — perfil JSON, o mais fácil

Agama é um **serviço com API REST e perfil JSON**, não um instalador monolítico.
A GUI gera o perfil e a ISO sobe com `agama auto --profile`:

```json
{
  "software": { "patterns": ["kde"] },
  "users": [{ "userName": "user", "fullName": "User", "password": "..." }],
  "storage": { "guided": { "target": { "disk": "/dev/vda" } } },
  "scripts": { "post": ["systemctl enable ..."] }
}
```

"Imitar o Calamares" aqui é montar esse JSON. Sem tocar no instalador.
Fixar (pin) a versão da ISO: a API ainda evolui rápido.

---

## 7. Catálogo multi-base (o ativo mais valioso)

O mesmo "KDE" tem nome diferente em cada base.

| Capacidade | Debian/Ubuntu | Arch | Fedora | openSUSE |
|---|---|---|---|---|
| KDE | `task-kde-desktop` | `plasma-meta` | `@kde-desktop` | `patterns-kde-kde` |
| GNOME | `task-gnome-desktop` | `gnome` | `@gnome-desktop` | `patterns-gnome-gnome` |
| XFCE | `task-xfce-desktop` | `xfce4` | `@xfce-desktop` | `patterns-xfce-xfce` |
| Hyprland | `hyprland` (unstable) | `hyprland` | COPR | repo OBS |
| Firefox | `firefox-esr` | `firefox` | `firefox` | `MozillaFirefox` |

```yaml
# catalog/desktops.yaml
kde:
  label: "KDE Plasma"
  icon: icons/kde.svg
  size: { debian: "1.8 GB", ubuntu: "1.8 GB", arch: "1.4 GB",
          fedora: "1.7 GB", opensuse: "1.6 GB" }
  pkgs:
    debian:   [task-kde-desktop]
    ubuntu:   [kubuntu-desktop]
    arch:     [plasma-meta, kde-applications]
    fedora:   ["@kde-desktop"]
    opensuse: [patterns-kde-kde]
```

Arquivos: `catalog/desktops.yaml`, `catalog/wms.yaml`, `catalog/apps.yaml`.

**Fonte única de verdade:** um script exporta o catálogo para JSON, consumido pelo
app Python **e** pelo site do GitHub Pages. Sem duplicação.

---

## 8. Estrutura do repositório

```
distroforge/
├── app/                          # PySide6
│   ├── main.py
│   ├── wizard/{base,branding,catalog,build}_page.py
│   └── log_view.py               # stream do build
├── core/
│   ├── profile.py                # schema pydantic
│   ├── catalog.py                # capacidade → pacote por base
│   └── orchestrator.py           # profile → builder + adapter → ISO
├── builders/
│   ├── base.py                   # ABC
│   ├── livebuild.py              # debian, ubuntu
│   ├── archiso.py                # arch
│   ├── lorax.py                  # fedora
│   └── kiwi.py                   # opensuse
├── installers/
│   ├── base.py                   # ABC
│   ├── calamares.py
│   ├── anaconda.py
│   └── agama.py
├── catalog/
│   ├── desktops.yaml
│   ├── wms.yaml
│   └── apps.yaml
├── assets/branding/
├── scripts/
│   └── export_catalog.py         # YAML → JSON para o site
├── tests/
│   └── vm_install.sh             # qemu + instalação roteirizada
├── site/                         # GitHub Pages (ver §11)
├── .github/workflows/pages.yml
└── out/
```

---

## 9. Fase 0 — Prova de conceito (bloqueante)

**Objetivo:** ISO Debian mínima instala KDE pela rede via Calamares, em VM.
Se isso não fechar, o resto não existe.

### 9.1 Container

```bash
podman run --privileged --rm -it \
  -v "$PWD/work:/build:Z" \
  -w /build debian:trixie-slim bash

apt update && apt install -y live-build calamares xorriso squashfs-tools \
  mtools dosfstools rsync wget
```

### 9.2 Configuração live-build

```bash
lb config \
  --distribution trixie \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --archive-areas "main contrib non-free non-free-firmware" \
  --bootloaders "syslinux,grub-efi" \
  --debian-installer none \
  --memtest none \
  --apt-indices false \
  --firmware-chroot true \
  --bootappend-live "boot=live components quiet splash"
```

### 9.3 Listas de pacotes (mínimo, não desktop inteiro)

```
# config/package-lists/live.list.chroot
calamares
calamares-settings-debian
squashfs-tools
rsync
parted
efibootmgr
os-prober
network-manager
firmware-iwlwifi
firmware-realtek
# base mínima: xorg/wayland + terminal + editor + browser de texto
```

### 9.4 Overlay

- `/etc/calamares/` com `settings.conf`, `packagechooser.yaml`, `netinstall.yaml`, branding
- autologin do usuário live
- `.desktop` "Instalar MinhaDistro" na área de trabalho
- passo de rede antes do Calamares (`nmtui` via `shellprocess`)

### 9.5 Build e teste

```bash
lb build
qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm \
  -cdrom live-image-amd64.hybrid.iso -boot d
```

### 9.6 Critérios de aceite

- [ ] ISO boota em BIOS **e** UEFI (com Secure Boot ligado)
- [ ] Wi-Fi conecta no live (firmware + `nmtui`)
- [ ] Calamares abre e mostra `packagechooser` com ≥ 3 desktops
- [ ] KDE baixa e instala pela rede
- [ ] Sistema instalado boota e tem `sources.list` funcional
- [ ] `apt update && apt upgrade` funciona no sistema instalado

---

## 10. Roadmap

| Fase | Entrega | Esforço |
|---|---|---|
| **0** | PoC manual Debian + Calamares + netinstall em VM | 3–5 dias |
| **1** | `core/` (perfil, catálogo, orquestrador) + CLI `distroforge build profile.yaml` | 1 semana |
| **2** | GUI PySide6: wizard, log ao vivo, botão "testar no QEMU" | 1–2 semanas |
| **3** | Builder `archiso` + adapter Arch (Ubuntu entra de graça no `livebuild`) | 1–2 semanas |
| **4** | Catálogo rico (6 desktops, 4 WMs, ~40 apps), Wi-Fi, fallback offline | 1–2 semanas |
| **5** | **openSUSE**: builder `kiwi` + adapter Agama (JSON) | 2–3 semanas |
| **6** | **Fedora**: builder `lorax` + kickstart interativo → depois addon | 3–4 semanas |

**MVP (fases 0–4): ~5–6 semanas** → Debian, Ubuntu e Arch com netinstall real.

---

## 11. Página interativa no GitHub Pages

### 11.1 Objetivo

Uma landing page que **funciona como demo do produto**, não só documentação.
Quem chega no repo deve conseguir, sem instalar nada:

1. Montar uma distro virtual no navegador (base → desktop → apps).
2. Ver o **tamanho estimado da ISO** e do **download** em tempo real.
3. Ver o **`profile.yaml` gerado**, com botão de copiar/baixar.
4. Clicar por um **mock navegável do Calamares** (telas reais, dados falsos).
5. Ler arquitetura, roadmap e FAQ.

Tudo client-side, estático, sem backend. O catálogo YAML do repo é exportado
para JSON em build time → **site e app usam os mesmos dados**.

### 11.2 Stack

| Item | Escolha | Motivo |
|---|---|---|
| Framework | **Astro 5 + Svelte 5 (islands)** | HTML estático + JS só onde é interativo |
| Estilo | Tailwind CSS 4 | Rápido, consistente, dark mode trivial |
| Deploy | GitHub Actions → Pages | Zero servidor |
| Dados | `catalog/*.yaml` → `site/src/data/catalog.json` | Fonte única |

Alternativa aceitável: Vite + React + TS. Astro é preferível porque a maior parte
do site é conteúdo e só o configurador precisa de JS.

### 11.3 Estrutura

```
site/
├── astro.config.mjs
├── package.json
├── src/
│   ├── layouts/Base.astro
│   ├── pages/index.astro            # hero + demo + docs + roadmap
│   ├── components/
│   │   ├── Hero.svelte
│   │   ├── Configurator.svelte      # wizard 4 passos (ilha)
│   │   ├── ProfilePreview.svelte    # YAML ao vivo + copiar
│   │   ├── SizeMeter.svelte         # ISO vs download
│   │   ├── InstallerMock.svelte     # mock do Calamares (ilha)
│   │   ├── BackendMatrix.astro
│   │   ├── Roadmap.astro
│   │   └── Faq.astro
│   └── data/catalog.json            # gerado
└── public/                          # logo, favicon, screenshots
```

### 11.4 O configurador (peça central)

Estado: `{ base, desktop, apps[], branding }`.

- **Passo 1 — Base:** cards Debian / Ubuntu / Arch (Fedora e openSUSE como "em breve").
- **Passo 2 — Desktop/WM:** grid com ícone, nome e tamanho **daquela base**.
- **Passo 3 — Apps:** checkboxes por categoria (navegador, office, mídia, dev, jogos).
- **Passo 4 — Resumo:** ISO estimada, download estimado, `profile.yaml` ao vivo,
  botões **Copiar** e **Baixar**.

Regras de UI:
- Tamanhos recalculam ao trocar base (valores vêm do catálogo, não hardcoded).
- Aviso claro: "instalação exige internet (~1,5–3 GB)".
- `localStorage` para preservar a seleção.
- Mobile-first; o wizard vira coluna única.
- Acessibilidade: foco visível, labels reais, `aria-live` nos totais.

### 11.5 Mock do instalador

Telas estáticas em HTML/CSS imitando o Calamares: welcome → partição → usuário →
packagechooser → netinstall → progresso → fim. Navegável com botões "Avançar/Voltar".
Serve para o visitante entender o resultado sem baixar 900 MB.

### 11.6 Workflow de deploy

```yaml
# .github/workflows/pages.yml
name: pages
on:
  push: { branches: [main] }
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: site/package-lock.json }
      - run: python3 scripts/export_catalog.py > site/src/data/catalog.json
      - run: npm ci && npm run build
        working-directory: site
      - uses: actions/upload-pages-artifact@v3
        with: { path: site/dist }
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Configuração no GitHub: **Settings → Pages → Source: GitHub Actions**.
URL: `https://<user>.github.io/distroforge/` (definir `base: '/distroforge'` no Astro).

### 11.7 Conteúdo da página

1. Hero: nome, tagline ("Monte sua distro Linux. Escolha a base, o desktop e os apps."), CTA para o configurador.
2. Demo interativa (§11.4).
3. Mock do instalador (§11.5).
4. "Como funciona" — diagrama builder × installer.
5. Matriz de backends (tabela §5).
6. Catálogo suportado (gerado do JSON).
7. Roadmap com fases e status.
8. FAQ (netinstall vs offline, requisitos, Secure Boot, licenças).
9. Footer: licença, links, "não afiliado a Debian/Ubuntu/Arch".

### 11.8 Esforço

| Entrega | Esforço |
|---|---|
| Astro + Tailwind + layout + deploy | 1 dia |
| Configurador + preview de perfil + tamanhos | 2–3 dias |
| Mock do Calamares | 1 dia |
| Conteúdo, i18n (pt-BR/en), acessibilidade | 1–2 dias |

**Total: ~1 semana.** Pode rodar em paralelo às fases 0–2 do app, porque depende
só do catálogo.

---

## 12. Riscos (por gravidade)

1. **Wi-Fi no live** — sem firmware + passo de conexão, netinstall é inútil em notebook.
   Não é opcional.
2. **`netinstall` falha silencioso** — keyring/mirror errado e o usuário termina sem
   desktop. Validar `apt update` / `pacman-key --init/--populate` antes de liberar.
3. **Anaconda addon** — quebra a cada release do Fedora. Começar com kickstart interativo.
4. **Agama** — API evolui rápido; pinar a versão da ISO.
5. **Secure Boot** — shim assinado no Debian/Ubuntu; Arch/Fedora exigem atenção.
6. **Matriz de testes** — cada combinação base × desktop. Automatizar `qemu` +
   install script desde a fase 0, senão viram 30 testes manuais.
7. **Marca** — não usar nome/logo Ubuntu (política de trademark rígida). Debian é mais
   permissivo, mas exige crédito e nome próprio.
8. **Disco/RAM por build** — 15–25 GB e 4–8 GB RAM; loop devices exigem container privilegiado.

---

## 13. Não-objetivos (por enquanto)

- Repositório próprio de pacotes (aptly/reprepro, GPG, CI) — projeto separado, meses.
- Atualizações OTA gerenciadas pela "distro".
- Assinatura de kernel próprio / Secure Boot customizado.
- Suporte a ARM, RISC-V.
- Instalador totalmente offline para as 5 bases.

---

## 14. Próximos passos

1. **Fase 0** (§9): PoC Debian + Calamares + netinstall em VM. Bloqueante.
2. Em paralelo: `site/` com catálogo exportado e configurador (§11).
3. Só depois da fase 0 verde: `core/` e CLI.

> Para implementar, trocar do agente de planejamento para o agente de build.
