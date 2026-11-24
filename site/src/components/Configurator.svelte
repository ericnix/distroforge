<script>
  import { onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import catalog from '../data/catalog.json';

  const bases = catalog.bases;
  const desktops = catalog.desktops;
  const wms = catalog.wms;
  const apps = catalog.apps;
  const categories = catalog.categories;

  const baseById = new Map(bases.map((b) => [b.id, b]));
  const allGraphical = [...desktops, ...wms];
  const STORAGE_KEY = 'distroforge:profile:v1';
  const BASE_MIN_MB = { debian: 1300, ubuntu: 1400, arch: 1000, fedora: 1350, opensuse: 1400 };

  const steps = [
    { n: 1, label: 'Base' },
    { n: 2, label: 'Desktop' },
    { n: 3, label: 'Programas' },
    { n: 4, label: 'Gerar' },
  ];

  const tones = [
    'from-brand-400 to-brand-600',
    'from-mint-400 to-mint-500',
    'from-amber-400 to-rose-400',
    'from-rose-400 to-brand-500',
    'from-brand-300 to-mint-400',
    'from-fog-300 to-brand-400',
  ];

  let step = $state(1);
  let name = $state('MinhaDistro');
  let base = $state('debian');
  let desktop = $state('kde');
  let copied = $state(false);

  const selected = new SvelteSet(apps.filter((a) => a.default).map((a) => a.id));

  const supports = (item, baseId) => Boolean(item.pkgs && item.pkgs[baseId]);

  const currentBase = $derived(baseById.get(base));
  const availDesktops = $derived(desktops.filter((d) => supports(d, base)));
  const availWms = $derived(wms.filter((w) => supports(w, base)));
  const availApps = $derived(apps.filter((a) => supports(a, base)));
  const graphicOptions = $derived([...availDesktops, ...availWms]);
  const desktopItem = $derived(allGraphical.find((d) => d.id === desktop));

  // Ao trocar de base, se o desktop escolhido não existir nela, cai para o primeiro válido.
  $effect(() => {
    if (!graphicOptions.some((item) => item.id === desktop) && graphicOptions.length) {
      desktop = graphicOptions[0].id;
    }
  });

  const desktopMb = $derived(desktopItem?.size?.[base] ?? 0);
  const appsMb = $derived(
    availApps.filter((a) => selected.has(a.id)).reduce((sum, a) => sum + (a.size?.[base] ?? 0), 0),
  );
  const downloadMb = $derived(desktopMb + appsMb);
  const isoMb = $derived((currentBase?.iso_size ?? 800) + 30);
  const diskMb = $derived((BASE_MIN_MB[base] ?? 1300) + Math.round(downloadMb * 1.9));
  const desktopShare = $derived(downloadMb > 0 ? Math.round((desktopMb / downloadMb) * 100) : 0);

  function fmt(mb) {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1).replace('.', ',')} GB`;
    return `${Math.round(mb)} MB`;
  }

  function slug(text) {
    return (
      text
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'minhadistro'
    );
  }

  function monogram(label) {
    const words = label.split(/\s+/).filter(Boolean);
    if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
    return label.slice(0, 2).toUpperCase();
  }

  function buildProfile() {
    const chosen = apps.filter((a) => selected.has(a.id) && supports(a, base)).map((a) => a.id);
    const safeName = (name.trim() || 'MinhaDistro').replace(/"/g, '');
    return [
      '# Perfil do DistroForge — revise antes de buildar',
      'meta:',
      `  name: "${safeName}"`,
      '  version: "1.0"',
      `  hostname: "${slug(name)}"`,
      `base: ${base}`,
      `variant: "${currentBase?.release ?? ''}"`,
      'arch: amd64',
      'install_mode: netinstall',
      `desktop_default: ${desktop}`,
      `apps_default: [${chosen.join(', ')}]`,
      'branding:',
      `  color: "${currentBase?.accent ?? '#3b82f6'}"`,
      `  iso_name: "${slug(name)}-1.0-amd64.iso"`,
      '',
    ].join('\n');
  }

  const profile = $derived(buildProfile());

  function toggleApp(id, on) {
    if (on) selected.add(id);
    else selected.delete(id);
  }

  function selectRecommended() {
    selected.clear();
    for (const app of apps) {
      if (app.default && supports(app, base)) selected.add(app.id);
    }
  }

  function clearApps() {
    selected.clear();
  }

  async function copyProfile() {
    try {
      await navigator.clipboard.writeText(profile);
    } catch {
      const area = document.createElement('textarea');
      area.value = profile;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    copied = true;
    setTimeout(() => (copied = false), 1800);
  }

  function downloadProfile() {
    const blob = new Blob([profile], { type: 'text/yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'profile.yaml';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  onMount(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (typeof saved.name === 'string' && saved.name.trim()) name = saved.name;
      if (saved.base && baseById.has(saved.base)) base = saved.base;
      if (typeof saved.desktop === 'string') desktop = saved.desktop;
      if (Array.isArray(saved.apps)) {
        selected.clear();
        for (const id of saved.apps) {
          if (apps.some((app) => app.id === id)) selected.add(id);
        }
      }
    } catch {
      /* estado salvo inválido: ignora */
    }
  });

  $effect(() => {
    if (typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ name, base, desktop, apps: [...selected] }),
      );
    } catch {
      /* storage cheio ou bloqueado */
    }
  });
</script>

<section id="montar" class="page scroll-mt-24 py-20">
  <div class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <p class="eyebrow">Configurador</p>
      <h2 class="h2 mt-2">Monte a sua, agora.</h2>
      <p class="muted mt-2 max-w-xl text-sm leading-relaxed">
        Escolha a base, o desktop e os programas. Os números são estimativas reais do catálogo — e
        tudo roda no seu navegador, nada é enviado.
      </p>
    </div>
    <span class="chip">
      <span class="size-1.5 rounded-full bg-mint-400"></span>
      demo offline · sem servidor
    </span>
  </div>

  <div
    class="mt-8 overflow-hidden rounded-2xl border border-ink-700 bg-ink-900/60 shadow-2xl shadow-black/40"
  >
    <!-- Indicador de passos -->
    <div class="flex items-center gap-1 overflow-x-auto border-b border-ink-700/70 px-3 py-3 sm:px-5">
      {#each steps as s}
        <button
          type="button"
          onclick={() => (step = s.n)}
          aria-current={step === s.n ? 'step' : undefined}
          aria-label={`Passo ${s.n}: ${s.label}`}
          class="flex shrink-0 items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors sm:px-3 {step ===
          s.n
            ? 'bg-brand-500/10 text-white'
            : 'text-fog-400 hover:bg-ink-800 hover:text-fog-200'}"
        >
          <span
            class="grid size-5 place-items-center rounded-full text-[11px] font-bold {step === s.n
              ? 'bg-brand-500 text-ink-950'
              : 'bg-ink-700 text-fog-300'}"
          >
            {#if s.n < step}
              <svg viewBox="0 0 16 16" class="size-3" fill="none" stroke="currentColor" stroke-width="2.5"
                stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 8.5l3 3 7-7" />
              </svg>
            {:else}
              {s.n}
            {/if}
          </span>
          <span class="hidden sm:inline">{s.label}</span>
        </button>
        {#if s.n < steps.length}
          <span class="h-px w-4 shrink-0 bg-ink-600" aria-hidden="true"></span>
        {/if}
      {/each}
    </div>

    <div class="grid lg:grid-cols-[minmax(0,1fr)_19rem]">
      <!-- Conteúdo do passo -->
      <div class="min-w-0 p-5 sm:p-7">
        {#if step === 1}
          <div class="max-w-md">
            <label for="distro-name" class="text-xs font-semibold uppercase tracking-wider text-fog-500">
              Nome da distro
            </label>
            <input
              id="distro-name"
              bind:value={name}
              maxlength="32"
              spellcheck="false"
              class="mt-2 w-full rounded-lg border border-ink-600 bg-ink-950 px-3 py-2.5 text-sm text-white placeholder:text-fog-500 focus:border-brand-500 focus:outline-none"
              placeholder="MinhaDistro"
            />
            <p class="mt-1.5 font-mono text-[11px] text-fog-500">
              hostname: {slug(name)} · iso: {slug(name)}-1.0-amd64.iso
            </p>
          </div>

          <fieldset class="mt-6">
            <legend class="text-xs font-semibold uppercase tracking-wider text-fog-500">
              Base do sistema
            </legend>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              {#each bases as b}
                <label
                  class="relative block rounded-xl border p-4 transition-colors {base === b.id
                    ? 'border-brand-500/70 bg-brand-500/10'
                    : 'border-ink-700 bg-ink-850 hover:border-ink-600'} {b.status !== 'stable'
                    ? 'cursor-not-allowed opacity-55'
                    : 'cursor-pointer'}"
                >
                  <input
                    type="radio"
                    name="base"
                    value={b.id}
                    bind:group={base}
                    disabled={b.status !== 'stable'}
                    class="sr-only"
                  />
                  <span class="flex items-start justify-between gap-3">
                    <span class="flex items-center gap-2.5">
                      <span class="size-2.5 rounded-full" style={`background:${b.accent}`}></span>
                      <span class="font-semibold text-white">{b.label}</span>
                    </span>
                    {#if b.status !== 'stable'}
                      <span class="chip !py-0.5 text-[10px]">em breve</span>
                    {/if}
                  </span>
                  <span class="mt-1 block text-xs text-fog-500">{b.release} · {b.pkg_manager}</span>
                  <span class="mt-2 block text-xs leading-relaxed text-fog-400">{b.summary}</span>
                  <span class="mt-3 block font-mono text-[11px] text-fog-500">ISO ≈ {fmt(b.iso_size)}</span>
                </label>
              {/each}
            </div>
            <p class="mt-3 text-xs text-fog-500">
              Fedora e openSUSE entram com instaladores próprios (Anaconda e Agama), em fases
              posteriores.
            </p>
          </fieldset>
        {:else if step === 2}
          <fieldset>
            <legend class="text-xs font-semibold uppercase tracking-wider text-fog-500">
              Ambiente gráfico completo
            </legend>
            <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {#each availDesktops as d, i}
                <label
                  class="cursor-pointer rounded-xl border p-4 transition-colors {desktop === d.id
                    ? 'border-brand-500/70 bg-brand-500/10'
                    : 'border-ink-700 bg-ink-850 hover:border-ink-600'}"
                >
                  <input type="radio" name="desktop" value={d.id} bind:group={desktop} class="sr-only" />
                  <span class="flex items-center gap-3">
                    <span
                      class="grid size-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br text-[11px] font-bold text-ink-950 {tones[
                        i % tones.length
                      ]}"
                      aria-hidden="true"
                    >
                      {monogram(d.label)}
                    </span>
                    <span class="min-w-0">
                      <span class="block truncate font-semibold text-white">{d.label}</span>
                      <span class="block font-mono text-[11px] text-fog-500">
                        {fmt(d.size?.[base] ?? 0)}
                      </span>
                    </span>
                  </span>
                  <span class="mt-2 block text-xs leading-relaxed text-fog-400">{d.summary}</span>
                </label>
              {/each}
            </div>
          </fieldset>

          <fieldset class="mt-7">
            <legend class="text-xs font-semibold uppercase tracking-wider text-fog-500">
              Window managers (você monta o resto)
            </legend>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              {#each availWms as w, i}
                <label
                  class="cursor-pointer rounded-xl border p-4 transition-colors {desktop === w.id
                    ? 'border-brand-500/70 bg-brand-500/10'
                    : 'border-ink-700 bg-ink-850 hover:border-ink-600'}"
                >
                  <input type="radio" name="desktop" value={w.id} bind:group={desktop} class="sr-only" />
                  <span class="flex items-center justify-between gap-3">
                    <span class="flex items-center gap-3">
                      <span
                        class="grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br text-[10px] font-bold text-ink-950 {tones[
                          (i + 3) % tones.length
                        ]}"
                        aria-hidden="true"
                      >
                        {monogram(w.label)}
                      </span>
                      <span class="font-semibold text-white">{w.label}</span>
                    </span>
                    <span class="font-mono text-[11px] text-fog-500">{fmt(w.size?.[base] ?? 0)}</span>
                  </span>
                  <span class="mt-2 block text-xs leading-relaxed text-fog-400">{w.summary}</span>
                  {#if w.note}
                    <span class="mt-2 block text-[11px] text-amber-400/90">{w.note}</span>
                  {/if}
                </label>
              {/each}
            </div>
            {#if availWms.length < 4}
              <p class="mt-3 text-xs text-fog-500">
                Alguns window managers não são empacotados em {currentBase?.label}; a lista mostra
                apenas os disponíveis para essa base.
              </p>
            {/if}
          </fieldset>
        {:else if step === 3}
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm text-fog-400">
              <span class="font-semibold text-white">{selected.size}</span> selecionados ·
              <span class="font-mono text-brand-300">{fmt(appsMb)}</span> de download
            </p>
            <div class="flex gap-2">
              <button type="button" class="btn-ghost !px-3 !py-1.5 text-xs" onclick={selectRecommended}>
                Recomendados
              </button>
              <button type="button" class="btn-ghost !px-3 !py-1.5 text-xs" onclick={clearApps}>
                Limpar
              </button>
            </div>
          </div>

          <div class="mt-5 space-y-6">
            {#each categories as category}
              {@const items = availApps.filter((a) => a.category === category.id)}
              {#if items.length}
                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-fog-500">
                    {category.label}
                  </h3>
                  <div class="mt-2 grid gap-1.5 sm:grid-cols-2">
                    {#each items as app}
                      <label
                        class="flex cursor-pointer items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 transition-colors hover:border-ink-700 hover:bg-ink-850"
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(app.id)}
                          onchange={(event) => toggleApp(app.id, event.currentTarget.checked)}
                          class="size-4 shrink-0 cursor-pointer accent-brand-500"
                        />
                        <span class="flex min-w-0 flex-1 items-center gap-2">
                          <span class="truncate text-sm text-fog-200">{app.label}</span>
                          {#if app.external}
                            <span
                              class="shrink-0 rounded border border-amber-400/30 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-400"
                              title="Requer repositório de terceiros"
                            >
                              repo extra
                            </span>
                          {/if}
                        </span>
                        <span class="shrink-0 font-mono text-[11px] text-fog-500">
                          {fmt(app.size?.[base] ?? 0)}
                        </span>
                      </label>
                    {/each}
                  </div>
                </div>
              {/if}
            {/each}
          </div>
        {:else}
          <div class="grid gap-3 sm:grid-cols-3">
            <div class="rounded-xl border border-ink-700 bg-ink-850 p-4">
              <p class="text-[11px] font-semibold uppercase tracking-wider text-fog-500">ISO</p>
              <p class="mt-1 font-mono text-xl font-semibold text-white">{fmt(isoMb)}</p>
              <p class="mt-1 text-[11px] text-fog-500">live + instalador</p>
            </div>
            <div class="rounded-xl border border-brand-500/30 bg-brand-500/5 p-4">
              <p class="text-[11px] font-semibold uppercase tracking-wider text-brand-300">
                Download
              </p>
              <p class="mt-1 font-mono text-xl font-semibold text-white">{fmt(downloadMb)}</p>
              <p class="mt-1 text-[11px] text-fog-500">durante a instalação</p>
            </div>
            <div class="rounded-xl border border-ink-700 bg-ink-850 p-4">
              <p class="text-[11px] font-semibold uppercase tracking-wider text-fog-500">No disco</p>
              <p class="mt-1 font-mono text-xl font-semibold text-white">{fmt(diskMb)}</p>
              <p class="mt-1 text-[11px] text-fog-500">instalado, aprox.</p>
            </div>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <span class="chip">{currentBase?.label} {currentBase?.release}</span>
            <span class="chip">{desktopItem?.label}</span>
            <span class="chip">{currentBase?.installer}</span>
            <span class="chip">{selected.size} apps</span>
          </div>

          <div class="mt-5 overflow-hidden rounded-xl border border-ink-700">
            <div class="flex items-center justify-between border-b border-ink-700 bg-ink-850 px-4 py-2.5">
              <span class="font-mono text-[11px] text-fog-400">profile.yaml</span>
              <div class="flex gap-2">
                <button type="button" class="btn-ghost !px-2.5 !py-1 text-[11px]" onclick={copyProfile}>
                  {#if copied}
                    <svg viewBox="0 0 16 16" class="size-3.5 text-mint-400" fill="none" stroke="currentColor"
                      stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M3 8.5l3 3 7-7" />
                    </svg>
                    Copiado
                  {:else}
                    Copiar
                  {/if}
                </button>
                <button type="button" class="btn-ghost !px-2.5 !py-1 text-[11px]" onclick={downloadProfile}>
                  Baixar
                </button>
              </div>
            </div>
            <pre
              class="thin-scroll max-h-80 overflow-auto bg-ink-950 p-4 font-mono text-[11.5px] leading-relaxed text-fog-300"><code>{profile}</code></pre>
          </div>

          <p class="mt-4 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2.5 text-xs leading-relaxed text-amber-400/90">
            A instalação exige internet (Wi-Fi ou cabo) para baixar o desktop e os programas do
            repositório da base. Sem rede, a ISO ainda entrega um sistema mínimo funcional.
          </p>
        {/if}
      </div>

      <!-- Resumo persistente -->
      <aside class="border-t border-ink-700/70 bg-ink-950/40 p-5 sm:p-6 lg:border-t-0 lg:border-l">
        <div class="flex items-center justify-between">
          <h3 class="text-[11px] font-semibold uppercase tracking-[0.16em] text-fog-500">Resumo</h3>
          <span class="size-2 rounded-full" style={`background:${currentBase?.accent}`} aria-hidden="true"
          ></span>
        </div>

        <p class="mt-3 truncate text-sm font-semibold text-white">{name.trim() || 'MinhaDistro'}</p>
        <p class="text-xs text-fog-500">hostname {slug(name)}</p>

        <div class="mt-5 h-2 flex overflow-hidden rounded-full bg-ink-800" aria-hidden="true">
          <span class="bg-brand-500" style={`width:${desktopShare}%`}></span>
          <span class="bg-mint-500" style={`width:${100 - desktopShare}%`}></span>
        </div>
        <div class="mt-2 flex justify-between text-[10px] text-fog-500">
          <span><span class="mr-1 inline-block size-1.5 rounded-full bg-brand-500"></span>desktop</span>
          <span><span class="mr-1 inline-block size-1.5 rounded-full bg-mint-500"></span>apps</span>
        </div>

        <dl class="mt-5 space-y-2.5 text-sm" aria-live="polite">
          <div class="flex items-baseline justify-between gap-2">
            <dt class="text-fog-400">ISO</dt>
            <dd class="font-mono text-fog-200">{fmt(isoMb)}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-2">
            <dt class="text-fog-400">Download</dt>
            <dd class="font-mono text-brand-300">{fmt(downloadMb)}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-2">
            <dt class="text-fog-400">No disco</dt>
            <dd class="font-mono text-fog-200">{fmt(diskMb)}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-2">
            <dt class="text-fog-400">Base</dt>
            <dd class="text-fog-200">{currentBase?.label}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-2">
            <dt class="text-fog-400">Desktop</dt>
            <dd class="truncate text-fog-200">{desktopItem?.label}</dd>
          </div>
        </dl>

        <div class="mt-5 rounded-lg border border-ink-700 bg-ink-900/70 p-3">
          <p class="text-[11px] leading-relaxed text-fog-500">
            Estimativa baseada no catálogo: pacotes comprimidos no download, expandidos no disco.
            Tempo típico de instalação: 8–20 min.
          </p>
        </div>
      </aside>
    </div>

    <div class="flex items-center justify-between gap-3 border-t border-ink-700/70 px-5 py-4 sm:px-7">
      <button
        type="button"
        class="btn-quiet"
        onclick={() => (step = Math.max(1, step - 1))}
        disabled={step === 1}
      >
        <svg viewBox="0 0 16 16" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M10 3L5 8l5 5" />
        </svg>
        Voltar
      </button>

      <div class="flex items-center gap-3">
        <span class="hidden text-xs text-fog-500 sm:inline">passo {step} de {steps.length}</span>
        <button
          type="button"
          class="btn-primary"
          onclick={() => (step < steps.length ? (step += 1) : downloadProfile())}
        >
          {step === steps.length ? 'Baixar profile.yaml' : 'Continuar'}
          <svg viewBox="0 0 16 16" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3l5 5-5 5" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</section>
