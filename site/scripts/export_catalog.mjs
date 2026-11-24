#!/usr/bin/env node
/**
 * Exporta catalog/*.yaml para site/src/data/catalog.json.
 *
 * Fonte única de verdade: o app Python, o site e o Cloudflare Pages consomem o
 * mesmo JSON gerado daqui. Só depende de Node (pacote `yaml`).
 *
 * Uso:
 *   node scripts/export_catalog.mjs            # escreve o arquivo
 *   node scripts/export_catalog.mjs --stdout   # imprime (para debug/CI)
 */

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = path.resolve(SITE, '..');
const CATALOG_DIR = path.join(ROOT, 'catalog');
const OUT_PATH = path.join(SITE, 'src', 'data', 'catalog.json');

const FILES = {
  bases: 'bases.yaml',
  desktops: 'desktops.yaml',
  wms: 'wms.yaml',
  apps: 'apps.yaml',
};

async function load(name) {
  const file = path.join(CATALOG_DIR, name);
  let raw;
  try {
    raw = await readFile(file, 'utf8');
  } catch {
    fail(`catálogo não encontrado: ${file}`);
  }
  try {
    return YAML.parse(raw);
  } catch (error) {
    fail(`YAML inválido em ${name}: ${error.message}`);
  }
}

function fail(message) {
  console.error(`erro: ${message}`);
  process.exit(1);
}

function validate(data) {
  const problems = [];
  const baseIds = new Set(data.bases.map((base) => base.id));

  for (const group of ['desktops', 'wms']) {
    for (const item of data[group]) {
      for (const baseId of Object.keys(item.pkgs ?? {})) {
        if (!baseIds.has(baseId)) {
          problems.push(`${group}/${item.id}: base desconhecida "${baseId}"`);
        }
      }
      if (!item.pkgs || Object.keys(item.pkgs).length === 0) {
        problems.push(`${group}/${item.id}: sem pacotes para base alguma`);
      }
    }
  }

  const categoryIds = new Set(data.categories.map((category) => category.id));
  const seen = new Set();
  for (const app of data.apps) {
    if (seen.has(app.id)) problems.push(`apps: id duplicado "${app.id}"`);
    seen.add(app.id);
    if (!categoryIds.has(app.category)) {
      problems.push(`apps/${app.id}: categoria desconhecida "${app.category}"`);
    }
    if (!app.pkgs || Object.keys(app.pkgs).length === 0) {
      problems.push(`apps/${app.id}: sem pacotes`);
    }
  }

  return problems;
}

async function build() {
  const [basesDoc, desktopsDoc, wmsDoc, appsDoc] = await Promise.all([
    load(FILES.bases),
    load(FILES.desktops),
    load(FILES.wms),
    load(FILES.apps),
  ]);

  const data = {
    generated: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    bases: basesDoc.bases,
    desktops: desktopsDoc.desktops,
    wms: wmsDoc.wms,
    categories: appsDoc.categories,
    apps: appsDoc.apps,
  };

  const problems = validate(data);
  if (problems.length > 0) {
    fail(`catálogo inválido:\n  - ${problems.join('\n  - ')}`);
  }

  return data;
}

const data = await build();
const payload = `${JSON.stringify(data, null, 2)}\n`;

if (process.argv.includes('--stdout')) {
  process.stdout.write(payload);
} else {
  await mkdir(path.dirname(OUT_PATH), { recursive: true });
  await writeFile(OUT_PATH, payload, 'utf8');
  console.log(
    `${path.relative(ROOT, OUT_PATH)}: ` +
      `${data.bases.length} bases, ${data.desktops.length} desktops, ` +
      `${data.wms.length} WMs, ${data.apps.length} apps`,
  );
}
