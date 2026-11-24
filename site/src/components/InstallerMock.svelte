<script>
  const screens = [
    { key: 'welcome', label: 'Boas-vindas' },
    { key: 'locale', label: 'Idioma' },
    { key: 'disk', label: 'Disco' },
    { key: 'user', label: 'Usuário' },
    { key: 'desktop', label: 'Desktop' },
    { key: 'apps', label: 'Programas' },
    { key: 'progress', label: 'Instalar' },
    { key: 'done', label: 'Concluído' },
  ];

  const desktopOptions = [
    { id: 'kde', label: 'KDE Plasma', size: '1,8 GB' },
    { id: 'gnome', label: 'GNOME', size: '1,6 GB' },
    { id: 'xfce', label: 'XFCE', size: '700 MB' },
    { id: 'hypr', label: 'Hyprland', size: '420 MB' },
  ];

  const appOptions = [
    { id: 'firefox', label: 'Firefox', size: '210 MB' },
    { id: 'libreoffice', label: 'LibreOffice', size: '480 MB' },
    { id: 'vlc', label: 'VLC', size: '95 MB' },
    { id: 'git', label: 'Git', size: '45 MB' },
    { id: 'steam', label: 'Steam', size: '380 MB' },
  ];

  let index = $state(0);
  let desktop = $state('kde');
  let checkedApps = $state(['firefox', 'libreoffice', 'vlc', 'git']);

  const screen = $derived(screens[index]);
  const progress = $derived(Math.round(((index + 1) / screens.length) * 100));
  const isLast = $derived(index === screens.length - 1);

  function next() {
    if (isLast) index = 0;
    else index += 1;
  }

  function toggleApp(id) {
    checkedApps = checkedApps.includes(id)
      ? checkedApps.filter((item) => item !== id)
      : [...checkedApps, id];
  }
</script>

<section id="instalador" class="page scroll-mt-24 py-20">
  <div class="max-w-2xl">
    <p class="eyebrow">Prévia</p>
    <h2 class="h2 mt-2">O que o usuário final vê.</h2>
    <p class="muted mt-2 text-sm leading-relaxed">
      Uma simulação navegável das telas do Calamares. Os dados são de exemplo — mas a ordem dos
      passos é a real: disco, usuário, desktop e programas, tudo antes de baixar qualquer pacote.
    </p>
  </div>

  <div
    class="mt-8 overflow-hidden rounded-xl border border-ink-600 bg-ink-950 shadow-2xl shadow-black/50"
  >
    <!-- Barra de título -->
    <div class="flex items-center gap-3 border-b border-ink-700 bg-ink-900 px-4 py-2.5">
      <div class="flex gap-1.5" aria-hidden="true">
        <span class="size-2.5 rounded-full bg-rose-400/80"></span>
        <span class="size-2.5 rounded-full bg-amber-400/80"></span>
        <span class="size-2.5 rounded-full bg-mint-400/80"></span>
      </div>
      <p class="truncate font-mono text-[11px] text-fog-500">
        MinhaDistro 1.0 — Instalação · Calamares
      </p>
      <span class="ml-auto rounded border border-amber-400/30 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400">
        simulação
      </span>
    </div>

    <div class="flex min-h-[27rem]">
      <!-- Passos -->
      <nav class="hidden w-48 shrink-0 border-r border-ink-800 bg-ink-900/50 p-3 sm:block" aria-label="Passos da simulação">
        <ol class="space-y-0.5">
          {#each screens as item, i}
            <li>
              <button
                type="button"
                onclick={() => (index = i)}
                aria-current={i === index ? 'step' : undefined}
                class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] transition-colors {i ===
                index
                  ? 'bg-brand-500/10 font-medium text-white'
                  : i < index
                    ? 'text-fog-500 hover:bg-ink-800'
                    : 'text-fog-500 hover:bg-ink-800'}"
              >
                <span
                  class="grid size-4 shrink-0 place-items-center rounded-full text-[9px] {i === index
                    ? 'bg-brand-500 text-ink-950'
                    : i < index
                      ? 'bg-mint-400/20 text-mint-400'
                      : 'bg-ink-700 text-fog-500'}"
                >
                  {#if i < index}
                    <svg viewBox="0 0 16 16" class="size-2.5" fill="none" stroke="currentColor"
                      stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M3 8.5l3 3 7-7" />
                    </svg>
                  {:else}
                    {i + 1}
                  {/if}
                </span>
                {item.label}
              </button>
            </li>
          {/each}
        </ol>
      </nav>

      <!-- Conteúdo -->
      <div class="flex min-w-0 flex-1 flex-col">
        <div class="flex-1 p-5 sm:p-7">
          {#if screen.key === 'welcome'}
            <h3 class="text-lg font-bold text-white">Bem-vindo ao MinhaDistro 1.0</h3>
            <p class="mt-2 max-w-md text-sm leading-relaxed text-fog-400">
              Este assistente vai instalar o sistema no seu computador. Você escolhe o disco, o
              usuário, o ambiente gráfico e os programas — o resto é baixado do repositório oficial
              da base.
            </p>
            <div class="mt-6 grid max-w-md grid-cols-3 gap-2">
              {#each [['Base', 'Debian 13'], ['Desktop', 'KDE Plasma'], ['Download', '2,6 GB']] as [k, v]}
                <div class="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2.5">
                  <p class="text-[9px] font-semibold uppercase tracking-wider text-fog-500">{k}</p>
                  <p class="mt-0.5 text-xs font-medium text-fog-200">{v}</p>
                </div>
              {/each}
            </div>
            <p class="mt-6 text-xs text-fog-500">A instalação leva de 8 a 20 minutos com internet estável.</p>
          {:else if screen.key === 'locale'}
            <h3 class="text-lg font-bold text-white">Idioma e teclado</h3>
            <div class="mt-5 max-w-sm space-y-3">
              {#each [['Idioma', 'Português (Brasil)'], ['Teclado', 'ABNT2'], ['Fuso horário', 'America/Sao_Paulo']] as [k, v]}
                <label class="block">
                  <span class="text-[11px] font-medium text-fog-500">{k}</span>
                  <span class="mt-1 flex items-center justify-between rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-sm text-fog-200">
                    {v}
                    <svg viewBox="0 0 16 16" class="size-3 text-fog-500" fill="none" stroke="currentColor"
                      stroke-width="2" stroke-linecap="round" aria-hidden="true">
                      <path d="M4 6l4 4 4-4" />
                    </svg>
                  </span>
                </label>
              {/each}
            </div>
          {:else if screen.key === 'disk'}
            <h3 class="text-lg font-bold text-white">Particionamento</h3>
            <p class="mt-1 text-xs text-fog-500">Escolha onde instalar. O disco inteiro será apagado.</p>

            <div class="mt-5 rounded-lg border border-ink-600 bg-ink-900 p-3.5">
              <div class="flex items-center justify-between text-xs">
                <span class="font-mono text-fog-200">/dev/nvme0n1</span>
                <span class="text-fog-500">512 GB</span>
              </div>
              <div class="mt-2.5 flex h-7 overflow-hidden rounded-md border border-ink-700" aria-hidden="true">
                <span class="grid w-[14%] place-items-center bg-ink-600 text-[9px] text-fog-300">EFI</span>
                <span class="grid w-[12%] place-items-center bg-brand-600/70 text-[9px] text-white">swap</span>
                <span class="grid flex-1 place-items-center bg-brand-500/40 text-[9px] text-brand-100">
                  raiz (ext4)
                </span>
              </div>
            </div>

            <div class="mt-4 space-y-2">
              <div class="flex items-center gap-2.5 rounded-lg border border-brand-500/60 bg-brand-500/10 px-3 py-2.5">
                <span class="grid size-4 place-items-center rounded-full border-2 border-brand-400">
                  <span class="size-1.5 rounded-full bg-brand-400"></span>
                </span>
                <span class="text-sm text-fog-100">Apagar disco e instalar</span>
              </div>
              <div class="flex items-center gap-2.5 rounded-lg border border-ink-700 px-3 py-2.5">
                <span class="size-4 rounded-full border-2 border-ink-600"></span>
                <span class="text-sm text-fog-400">Particionamento manual</span>
              </div>
            </div>
          {:else if screen.key === 'user'}
            <h3 class="text-lg font-bold text-white">Sua conta</h3>
            <div class="mt-5 flex max-w-sm flex-col gap-3">
              <div class="flex items-center gap-3">
                <span class="grid size-11 place-items-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-sm font-bold text-ink-950">U</span>
                <div class="text-xs text-fog-500">Avatar gerado automaticamente</div>
              </div>
              {#each [['Nome completo', 'Usuário Exemplo'], ['Nome de usuário', 'usuario'], ['Senha', '••••••••']] as [k, v]}
                <label class="block">
                  <span class="text-[11px] font-medium text-fog-500">{k}</span>
                  <span class="mt-1 block rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 font-mono text-sm text-fog-200">{v}</span>
                </label>
              {/each}
              <label class="flex items-center gap-2 text-xs text-fog-400">
                <span class="grid size-3.5 place-items-center rounded border border-brand-400 bg-brand-500">
                  <svg viewBox="0 0 16 16" class="size-2.5 text-ink-950" fill="none" stroke="currentColor"
                    stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M3 8.5l3 3 7-7" />
                  </svg>
                </span>
                Entrar automaticamente sem senha
              </label>
            </div>
          {:else if screen.key === 'desktop'}
            <h3 class="text-lg font-bold text-white">Ambiente gráfico</h3>
            <p class="mt-1 text-xs text-fog-500">Você pode instalar outro depois pelos repositórios.</p>
            <div class="mt-4 grid gap-2 sm:grid-cols-2">
              {#each desktopOptions as option}
                <button
                  type="button"
                  onclick={() => (desktop = option.id)}
                  aria-pressed={desktop === option.id}
                  class="rounded-lg border p-3 text-left transition-colors {desktop === option.id
                    ? 'border-brand-500/70 bg-brand-500/10'
                    : 'border-ink-700 bg-ink-900 hover:border-ink-600'}"
                >
                  <span class="flex items-center justify-between">
                    <span class="text-sm font-medium text-fog-100">{option.label}</span>
                    <span class="font-mono text-[10px] text-fog-500">{option.size}</span>
                  </span>
                  <span class="mt-1 block text-[11px] text-fog-500">
                    {desktop === option.id ? 'selecionado' : 'clique para escolher'}
                  </span>
                </button>
              {/each}
            </div>
          {:else if screen.key === 'apps'}
            <h3 class="text-lg font-bold text-white">Programas</h3>
            <p class="mt-1 text-xs text-fog-500">Baixados do repositório oficial durante a instalação.</p>
            <div class="mt-4 max-w-md space-y-1">
              {#each appOptions as app}
                <label class="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 hover:bg-ink-900">
                  <span
                    class="grid size-4 place-items-center rounded border {checkedApps.includes(app.id)
                      ? 'border-brand-400 bg-brand-500'
                      : 'border-ink-600 bg-ink-900'}"
                  >
                    {#if checkedApps.includes(app.id)}
                      <svg viewBox="0 0 16 16" class="size-2.5 text-ink-950" fill="none" stroke="currentColor"
                        stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M3 8.5l3 3 7-7" />
                      </svg>
                    {/if}
                  </span>
                  <input
                    type="checkbox"
                    class="sr-only"
                    checked={checkedApps.includes(app.id)}
                    onchange={() => toggleApp(app.id)}
                  />
                  <span class="flex-1 text-sm text-fog-200">{app.label}</span>
                  <span class="font-mono text-[10px] text-fog-500">{app.size}</span>
                </label>
              {/each}
            </div>
            <p class="mt-3 text-[11px] text-fog-500">
              {checkedApps.length} selecionados · cerca de 830 MB de download
            </p>
          {:else if screen.key === 'progress'}
            <h3 class="text-lg font-bold text-white">Instalando…</h3>
            <div class="mt-5 max-w-md">
              <div class="flex items-baseline justify-between text-xs">
                <span class="text-fog-400">Baixando pacotes</span>
                <span class="font-mono text-brand-300">68%</span>
              </div>
              <div class="mt-2 h-2 overflow-hidden rounded-full bg-ink-800">
                <div class="h-full w-[68%] rounded-full bg-gradient-to-r from-brand-500 to-brand-400"></div>
              </div>
              <div class="mt-4 space-y-1 rounded-lg border border-ink-700 bg-ink-950 p-3 font-mono text-[10.5px] leading-relaxed text-fog-500">
                <p><span class="text-mint-400">✓</span> particionando /dev/nvme0n1</p>
                <p><span class="text-mint-400">✓</span> extraindo sistema base</p>
                <p><span class="text-mint-400">✓</span> instalando kernel e initramfs</p>
                <p><span class="text-brand-400">→</span> baixando plasma-meta (412/607)</p>
                <p class="text-fog-600">→ aguardando configuração de rede…</p>
              </div>
            </div>
          {:else}
            <div class="flex max-w-md flex-col items-start">
              <span class="grid size-12 place-items-center rounded-full bg-mint-400/15">
                <svg viewBox="0 0 24 24" class="size-6 text-mint-400" fill="none" stroke="currentColor"
                  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </span>
              <h3 class="mt-4 text-lg font-bold text-white">Instalação concluída</h3>
              <p class="mt-2 text-sm leading-relaxed text-fog-400">
                Remova a mídia de instalação e reinicie. O sistema vai atualizar direto dos
                repositórios oficiais da base escolhida.
              </p>
              <button type="button" class="btn-primary mt-5" onclick={() => (index = 0)}>
                Reiniciar simulação
              </button>
            </div>
          {/if}
        </div>

        <!-- Rodapé do instalador -->
        <div class="flex items-center justify-between gap-3 border-t border-ink-800 bg-ink-900/60 px-4 py-3">
          <button
            type="button"
            class="btn-quiet !px-3 !py-1.5 text-xs"
            onclick={() => (index = Math.max(0, index - 1))}
            disabled={index === 0}
          >
            Voltar
          </button>

          <div class="flex items-center gap-3">
            <div class="hidden items-center gap-2 sm:flex" aria-hidden="true">
              <div class="h-1 w-24 overflow-hidden rounded-full bg-ink-800">
                <div class="h-full rounded-full bg-brand-500 transition-[width] duration-300" style={`width:${progress}%`}></div>
              </div>
              <span class="font-mono text-[10px] text-fog-500">{progress}%</span>
            </div>
            <button type="button" class="btn-primary !px-4 !py-1.5 text-xs" onclick={next}>
              {isLast ? 'Recomeçar' : index === screens.length - 2 ? 'Instalar' : 'Avançar'}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <p class="mt-3 text-xs text-fog-500">
    Simulação visual. No projeto real, estas telas são o Calamares (Debian, Ubuntu e Arch), o
    Anaconda via kickstart (Fedora) ou o Agama com perfil JSON (openSUSE).
  </p>
</section>
