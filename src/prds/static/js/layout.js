import { t } from './i18n.js';
import { getPrefs } from './prefs.js';

function sidebarFooterControls(sidebarActive) {
  const prefs = getPrefs();
  const locale = prefs.locale || 'zh';
  const theme = prefs.theme || 'light';
  const utilClass = (page) =>
    sidebarActive === page ? 'sidebar-util-link sidebar-util-active' : 'sidebar-util-link';

  return `
    <div class="app-sidebar-footer">
      <div id="llm-badge" class="sidebar-llm-badge hidden"></div>
      <button type="button" id="sb-locale-btn" class="sidebar-util-btn" title="${t('header.toggleLocale')}" aria-label="${t('header.toggleLocale')}">
        <span class="material-symbols-outlined">translate</span>
        <span class="sidebar-util-label">${t('sidebar.language')}</span>
        <span id="sb-locale-label" class="sidebar-util-meta">${locale === 'en' ? 'EN' : '中'}</span>
      </button>
      <button type="button" id="sb-theme-btn" class="sidebar-util-btn" title="${t('header.toggleTheme')}" aria-label="${t('header.toggleTheme')}">
        <span class="material-symbols-outlined" id="sb-theme-icon">${theme === 'dark' ? 'light_mode' : 'dark_mode'}</span>
        <span class="sidebar-util-label">${t('sidebar.theme')}</span>
        <span class="sidebar-util-meta">${theme === 'dark' ? t('sidebar.themeDark') : t('sidebar.themeLight')}</span>
      </button>
      <a href="#model" class="${utilClass('model')}">
        <span class="material-symbols-outlined">smart_toy</span>
        <span class="sidebar-util-label">${t('nav.model')}</span>
      </a>
      <a href="#settings" class="${utilClass('settings')}">
        <span class="material-symbols-outlined">settings</span>
        <span class="sidebar-util-label">${t('nav.settings')}</span>
      </a>
    </div>`;
}

export function renderSidebar(sidebarActive, simId = null) {
  const sid = simId || localStorage.getItem('prds_last_sim');
  const links = [
    { icon: 'account_tree', labelKey: 'sidebar.simulate', page: 'simulate' },
    { icon: 'query_stats', labelKey: 'sidebar.monitor', page: 'monitor', needsSim: true },
    { icon: 'table_chart', labelKey: 'sidebar.results', page: 'results', needsSim: true },
    { icon: 'hub', labelKey: 'sidebar.knowledge', page: 'knowledge', needsSim: true },
  ];
  return `
  <aside class="app-sidebar">
    <div class="app-sidebar-brand">
      <a href="#simulate" class="app-sidebar-logo">
        <span class="material-symbols-outlined text-primary text-2xl">auto_awesome</span>
        <span class="app-sidebar-logo-text">Odyssey</span>
      </a>
    </div>

    <div class="app-sidebar-section">
      <div class="text-xs text-on-surface-variant leading-snug">${t('sidebar.subtitle')}</div>
      ${sid ? `<div class="text-[10px] font-mono text-outline mt-1.5 truncate" title="${sid}">${sid.slice(0, 8)}…</div>` : ''}
    </div>

    <nav class="app-sidebar-nav">
      ${links.map(l => {
        const href = l.needsSim && sid ? `#${l.page}/${sid}` : `#${l.page}`;
        const disabled = l.needsSim && !sid;
        const active = sidebarActive === l.page;
        return `
        <a href="${disabled ? '#' : href}"
           class="sidebar-nav-link ${disabled ? 'sidebar-nav-disabled' : active ? 'sidebar-link-active' : 'sidebar-link-idle'}">
          <span class="material-symbols-outlined text-[20px]">${l.icon}</span>
          <span>${t(l.labelKey)}</span>
        </a>`;
      }).join('')}
    </nav>

    ${sidebarFooterControls(sidebarActive)}
  </aside>`;
}

export function pageShell(content, opts = {}) {
  const {
    sidebarActive = null,
    simId = null,
    noSidebar = false,
    mainClass = 'ml-60 min-h-screen',
  } = opts;
  return `
    ${noSidebar ? '' : renderSidebar(sidebarActive, simId)}
    <main class="${mainClass}">${content}</main>`;
}

export function syncSidebarControls() {
  const prefs = getPrefs();
  const locale = prefs.locale || 'zh';
  const theme = prefs.theme || 'light';
  const localeLabel = document.getElementById('sb-locale-label');
  const themeIcon = document.getElementById('sb-theme-icon');
  const themeBtn = document.getElementById('sb-theme-btn');
  if (localeLabel) localeLabel.textContent = locale === 'en' ? 'EN' : '中';
  if (themeIcon) themeIcon.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
  if (themeBtn) {
    const meta = themeBtn.querySelector('.sidebar-util-meta');
    if (meta) meta.textContent = theme === 'dark' ? t('sidebar.themeDark') : t('sidebar.themeLight');
  }
}

/** @deprecated use syncSidebarControls */
export function syncHeaderControls() {
  syncSidebarControls();
}

export async function initHealthBadge() {
  try {
    const h = await fetch('/health').then(r => r.json());
    const el = document.getElementById('llm-badge');
    if (el) {
      el.classList.remove('hidden');
      el.textContent = h.llm_configured ? t('badge.llm') : t('badge.unconfigured');
      el.className = `sidebar-llm-badge ${h.llm_configured ? 'sidebar-llm-live' : 'sidebar-llm-unconfigured'}`;
    }
  } catch (_) {}
}
