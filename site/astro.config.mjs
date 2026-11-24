import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import tailwindcss from '@tailwindcss/vite';

// Cloudflare Pages serve na raiz. Para GitHub Pages (subpasta), defina
// BASE_PATH=/nome-do-repo no build.
const base = process.env.BASE_PATH ?? '/';

export default defineConfig({
  site: process.env.SITE_URL ?? 'https://distroforge.pages.dev',
  base,
  trailingSlash: 'ignore',
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()],
  },
});
