const TOP_NAV = [
  { id: 'simulate', label: '模拟', hash: '#simulate' },
  { id: 'model', label: '模型', hash: '#model' },
  { id: 'settings', label: '设置', hash: '#settings' },
];

export function renderTopNav(topNavActive) {
  return `
  <header class="fixed top-0 w-full z-50 bg-surface/90 backdrop-blur-md border-b border-outline-variant flex items-center justify-between px-6 lg:px-12 h-16">
    <div class="flex items-center gap-10">
      <a href="#simulate" class="font-bold text-xl tracking-tight text-primary shrink-0">Odyssey</a>
      <nav class="hidden md:flex items-center gap-8">
        ${TOP_NAV.map(n => `
          <a href="${n.hash}" class="text-sm font-medium transition-colors pb-0.5 ${topNavActive === n.id ? 'nav-active text-primary' : 'text-on-surface-variant hover:text-primary'}">${n.label}</a>
        `).join('')}
      </nav>
    </div>
    <div class="flex items-center gap-3">
      <span id="llm-badge" class="hidden text-[10px] font-bold px-2 py-0.5 rounded-full bg-secondary/10 text-secondary"></span>
      <button type="button" class="material-symbols-outlined text-on-surface-variant hover:text-primary">notifications</button>
      <button type="button" class="material-symbols-outlined text-on-surface-variant hover:text-primary">account_circle</button>
    </div>
  </header>`;
}

export function renderSidebar(sidebarActive, simId = null) {
  const sid = simId || localStorage.getItem('prds_last_sim');
  const links = [
    { icon: 'account_tree', label: '新建推演', page: 'simulate' },
    { icon: 'query_stats', label: '实时监控', page: 'monitor', needsSim: true },
    { icon: 'table_chart', label: '决策矩阵', page: 'results', needsSim: true },
    { icon: 'hub', label: '知识图谱', page: 'knowledge', needsSim: true },
  ];
  return `
  <aside class="fixed left-0 top-16 h-[calc(100vh-64px)] w-64 bg-surface-container-low border-r border-outline-variant flex flex-col p-4 z-40">
    <div class="px-2 py-3 mb-2">
      <div class="text-base font-bold text-on-surface">PRDS 推演</div>
      <div class="text-xs text-on-surface-variant">平行世界决策模拟</div>
      ${sid ? `<div class="text-[10px] font-mono text-outline mt-1 truncate" title="${sid}">${sid.slice(0, 8)}…</div>` : ''}
    </div>
    <nav class="flex-1 space-y-1">
      ${links.map(l => {
        const href = l.needsSim && sid ? `#${l.page}/${sid}` : `#${l.page}`;
        const disabled = l.needsSim && !sid;
        return `
        <a href="${disabled ? '#' : href}"
           class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${disabled ? 'opacity-40 pointer-events-none' : sidebarActive === l.page ? 'text-primary bg-primary/10 font-bold' : 'text-on-surface-variant hover:bg-surface-container'}">
          <span class="material-symbols-outlined text-[20px]">${l.icon}</span>${l.label}
        </a>`;
      }).join('')}
    </nav>
  </aside>`;
}

export function pageShell(content, opts = {}) {
  const {
    topNav = 'simulate',
    sidebarActive = null,
    simId = null,
    noSidebar = false,
    mainClass = 'ml-64 mt-16 min-h-screen',
  } = opts;
  return `
    ${renderTopNav(topNav)}
    ${noSidebar ? '' : renderSidebar(sidebarActive, simId)}
    <main class="${mainClass}">${content}</main>`;
}

export async function initHealthBadge() {
  try {
    const h = await fetch('/health').then(r => r.json());
    const el = document.getElementById('llm-badge');
    if (el) {
      el.classList.remove('hidden');
      el.textContent = h.llm_configured ? 'LLM 已连接' : 'Mock 模式';
    }
  } catch (_) {}
}

export function topNavForPage(page) {
  if (page === 'model') return 'model';
  if (page === 'settings') return 'settings';
  return 'simulate';
}
