# DistroForge

Construtor de distros Linux com interface gráfica: escolha a base, o desktop e os
programas, e gere uma ISO **netinstall** com instalador. O sistema instalado atualiza
dos repositórios da própria base — é remaster com instalador, não uma distro
independente.

> **Status:** o site (este repositório) está pronto. O aplicativo desktop (PySide6) e o
> motor de build estão em planejamento — veja [`docs/PLAN.md`](docs/PLAN.md).

## O que tem aqui

- `site/` — página interativa (Astro + Svelte 5 + Tailwind 4), publicada no Cloudflare Pages.
- `catalog/` — fonte única de verdade: bases, desktops, window managers e apps, com o
  nome do pacote em cada distro.
- `site/scripts/export_catalog.mjs` — converte o catálogo YAML em JSON para o site
  (e, depois, para o app). Só depende de Node.
- `docs/PLAN.md` — plano completo: arquitetura, fases, riscos e backlog.

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

### Opção A — integração com o GitHub (recomendado)

1. No painel do Cloudflare, vá em **Workers & Pages → Create → Pages → Connect to Git**.
2. Selecione o repositório `distroforge`.
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
npx wrangler pages deploy dist --project-name distroforge
```

Na primeira vez o Wrangler pede login no navegador (ou use `CLOUDFLARE_API_TOKEN`).

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
