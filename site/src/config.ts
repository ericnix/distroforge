export const SITE = {
  name: 'DistroForge',
  short: 'DF',
  tagline: 'Monte sua distro Linux.',
  description:
    'Construtor de distros Linux com GUI: escolha a base, o desktop e os apps, e gere uma ISO netinstall com instalador Calamares.',
  license: 'GPL-3.0-or-later',
  minInstall: '~9 GB',
  repo: import.meta.env.PUBLIC_GITHUB_REPO ?? 'https://github.com/ericnix/distroforge',
  docs: import.meta.env.PUBLIC_DOCS_URL ?? 'https://github.com/ericnix/distroforge/blob/main/docs/PLAN.md',
} as const;
