# DistroForge

Construtor de distros Linux com interface gráfica: escolha a base, o desktop e os
programas, e gere uma ISO **netinstall** com instalador. O sistema instalado atualiza
dos repositórios da própria base — é remaster com instalador, não uma distro
independente.

> **Status:** o site está publicado em **https://distroforge-site.pages.dev**. Fases 0–3
> concluídas: **Debian, Ubuntu e Arch** geram ISO, instalam pelo Calamares baixando os
> pacotes da base e o sistema instalado boota no KDE Plasma (validado de ponta a ponta
> em VM — ver [`docs/FASE3.md`](docs/FASE3.md)). Faltam a matriz de testes de boot,
> UEFI/Secure Boot e Wi-Fi no live (fase 4); Fedora e openSUSE são as fases 5 e 6.
> Veja [`docs/PLAN.md`](docs/PLAN.md).

## O que tem aqui

- `site/` — página interativa (Astro + Svelte 5 + Tailwind 4), publicada no Cloudflare Pages.
- `src/distroforge/` — núcleo do construtor: perfil neutro, catálogo, adapters e CLI.
- `tests/` — testes do núcleo (57 casos: geração de árvore, sequências do Calamares,
  configs por base). **Não** rodam um install real — a validação de boot está em
  `docs/FASE3.md` e os scripts de VM em `df-poc/`.
- `catalog/` — fonte única de verdade: bases, desktops, window managers e apps, com o
  nome do pacote em cada distro.
- `site/scripts/export_catalog.mjs` — converte o catálogo YAML em JSON para o site
  (e, depois, para o app). Só depende de Node.
- `docs/PLAN.md` — plano completo: arquitetura, fases, riscos e backlog.

## App / CLI

```bash
uv venv --python 3.13
uv pip install -e ".[dev,gui]"
.venv/bin/pytest

.venv/bin/distroforge catalog --base debian
.venv/bin/distroforge init --name "Minha Distro" --base debian --desktop kde --out profile.yaml
.venv/bin/distroforge plan profile.yaml
.venv/bin/distroforge generate profile.yaml --out build   # árvore + /etc/calamares
.venv/bin/distroforge build profile.yaml --out out --dry-run
```

### GUI

```bash
.venv/bin/distroforge-gui     # ou: distroforge gui
```

Assistente em 5 passos — base, desktop, programas, personalizar e construir —
com resumo de tamanhos ao vivo, log do build em streaming e botão para testar
a ISO no QEMU. A GUI usa o mesmo `Orchestrator` da CLI.

`build` roda dentro de um container (`podman`/`docker`) da base escolhida, com
`--privileged` porque `live-build` e `mkarchiso` precisam de loop devices.

O perfil é o mesmo `profile.yaml` que o site gera no navegador: um arquivo feito
na página roda na CLI sem conversão.

### O que a CLI já faz

| Comando | Estado |
|---|---|
| `catalog` | lista bases, desktops, WMs e apps do catálogo |
| `init` | cria um perfil válido com os apps recomendados da base |
| `validate` / `plan` | valida e mostra pacotes, tamanhos e avisos |
| `generate` | escreve `auto/config`, package lists, overlay do Calamares e `build.sh` |
| `build` | gera e roda o `lb build` em container (Debian); Arch via `mkarchiso` |

### Bases

| Base | Builder | Instalador | Estado |
|---|---|---|---|
| Debian | `live-build` | Calamares | **validado** (fase 0/1) |
| Ubuntu | `live-build` (`--mode ubuntu`) | Calamares | **validado** (fase 1) |
| Arch | `archiso` | Calamares (AUR) | **validado** (fase 3) |
| Fedora | `lorax` | Anaconda/kickstart | fase 6 |
| openSUSE | `kiwi` | Agama (JSON) | fase 5 |

O Arch exigiu um adapter próprio: o `calamares` do AUR **não é o do Debian**
(falta `packagechooser`, os módulos de initramfs se chamam `initcpio`/`initcpiocfg`),
e o `mkarchiso` apaga `/boot`, o sync db e o cache de pacotes do squashfs — três
coisas que o alvo precisa e que só aparecem no minuto 35 de um install real.
A lista completa está em [`docs/FASE3.md`](docs/FASE3.md).

### Testar a ISO no QEMU

```bash
python3 scripts/qemu-test.py out/minha-distro-1.0-amd64.iso
```

Sobe a VM sem display (KVM se disponível), anexa um disco virtual de 20 GB,
pressiona Enter no menu e captura telas do boot em `shots/boot*.png`. Rode com
o diretório de saída fora de `/tmp` (que costuma ser tmpfs) — a instalação
grava vários GB no disco da VM. O progresso da fase 0 está em
[`docs/FASE0.md`](docs/FASE0.md) e a validação completa do Ubuntu e do Arch
(em com o wizard atravessando as páginas, o install, o boot do disco
instalado e a sessão do desktop) em [`docs/FASE3.md`](docs/FASE3.md).

Para exercitar o instalador inteiro (partição → usuário → desktop → netinstall):

```bash
uv pip install vncdotool
python3 scripts/qemu-install-test.py out/minha-distro-1.0-amd64.iso
```

O script dirige o Calamares por VNC e salva cada tela em `vm/shots/`.

Fedora e openSUSE ainda param com mensagem clara: os adapters Anaconda e Agama
entram nas fases 5 e 6.

## Rodar localmente

Requisitos: Node 22+.

```bash
cd site
npm install
npm run dev
```

Abra <http://localhost:4321/>. O `dev` exporta o catálogo automaticamente
(`predev` → `npm run catalog`).

Build estático:

```bash
cd site
npm run build      # roda o catalog e gera site/dist
npm run preview    # serve o dist localmente
```

## Publicar no Cloudflare Pages

O projeto está publicado em **https://distroforge-site.pages.dev**
(projeto `distroforge-site`; o nome `distroforge` já pertence a outra conta no
subdomínio `pages.dev`).

### Opção A — integração com o GitHub (recomendado)

1. No painel do Cloudflare, vá em **Workers & Pages → distroforge-site → Settings → Build**.
2. Clique em **Connect to Git** e selecione o repositório `distroforge`.
3. Configure o build:

   | Campo | Valor |
   |---|---|
   | Framework preset | Astro |
   | Root directory | `site` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Node version | `22` (variável `NODE_VERSION=22`) |

4. Deploy. Cada push na `main` gera um deploy de produção; PRs geram previews.

O `prebuild` cuida da exportação do catálogo, então não existe passo extra de Python.

### Opção B — upload direto com Wrangler

```bash
cd site
npm run build
npx wrangler pages deploy dist --project-name distroforge-site
```

Na primeira vez o Wrangler pede login no navegador (ou use `CLOUDFLARE_API_TOKEN`).

O mesmo caminho roda **automático** no CI: o job `deploy` do `ci.yml` publica
em cada push na `main` — mas só se os secrets `CLOUDFLARE_API_TOKEN` (e
`CLOUDFLARE_ACCOUNT_ID`) estiverem definidos em **Settings → Secrets and variables
→ Actions**. Sem eles o passo é emitido como *notice* e o CI continua verde,
então o workflow não quebra para quem ainda não configurou.

> Nota: o `wrangler` está em `devDependencies` do `site/` de propósito — sem
> isso o `npm ci` do CI não o instalaria e o `npx` baixaria uma versão não
> pinada a cada deploy.

## Editando o catálogo

Tudo em `catalog/*.yaml`. Regras rápidas:

- `size` é o download aproximado em MB **por base**.
- `pkgs` mapeia base → lista de pacotes. Se uma base não aparece, o item fica
  indisponível nela (a interface filtra sozinha).
- `default: true` marca apps pré-selecionados.
- `external: true` sinaliza pacote que exige repositório de terceiros.

Depois de editar, rode `npm run catalog` dentro de `site/` (ou apenas `npm run build`).
O script valida bases e categorias desconhecidas e falha com mensagem clara.

## Estrutura do site

```
site/
├── scripts/export_catalog.mjs  # YAML → JSON, com validação
├── src/
│   ├── config.ts               # nome, links, licença
│   ├── layouts/Base.astro
│   ├── pages/{index,404}.astro
│   ├── components/
│   │   ├── Configurator.svelte   # wizard: base → desktop → apps → perfil
│   │   ├── InstallerMock.svelte  # simulação navegável do Calamares
│   │   ├── Hero.astro
│   │   ├── HowItWorks.astro
│   │   ├── BackendMatrix.astro
│   │   ├── CatalogTable.astro
│   │   ├── Roadmap.astro
│   │   ├── Faq.astro
│   │   └── Footer.astro
│   └── data/catalog.json       # gerado, não versionado
└── public/favicon.svg
```

## Licença

[GPL-3.0-or-later](LICENSE). As distros geradas seguem as licenças das bases e dos
pacotes instalados.

Não afiliado a Debian, Ubuntu, Arch, Fedora ou openSUSE.
