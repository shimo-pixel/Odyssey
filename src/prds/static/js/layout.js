import { t } from './i18n.js';
import { getPrefs } from './prefs.js';
import { icon } from './icons.js';

const NAV_ICONS = {
  simulate: 'simulate',
  monitor: 'monitor',
  results: 'results',
  knowledge: 'knowledge',
};

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
        ${icon('translate', 'icon icon--md')}
        <span class="sidebar-util-label">${t('sidebar.language')}</span>
        <span id="sb-locale-label" class="sidebar-util-meta">${locale === 'en' ? 'EN' : '中'}</span>
      </button>
      <button type="button" id="sb-theme-btn" class="sidebar-util-btn" title="${t('header.toggleTheme')}" aria-label="${t('header.toggleTheme')}">
        <span id="sb-theme-icon" class="icon icon--md" aria-hidden="true">${icon(theme === 'dark' ? 'sun' : 'moon').replace(/^<span[^>]*>|<\/span>$/g, '')}</span>
        <span class="sidebar-util-label">${t('sidebar.theme')}</span>
        <span class="sidebar-util-meta">${theme === 'dark' ? t('sidebar.themeDark') : t('sidebar.themeLight')}</span>
      </button>
      <a href="#model" class="${utilClass('model')}">
        ${icon('model', 'icon icon--md')}
        <span class="sidebar-util-label">${t('nav.model')}</span>
      </a>
      <a href="#settings" class="${utilClass('settings')}">
        ${icon('settings', 'icon icon--md')}
        <span class="sidebar-util-label">${t('nav.settings')}</span>
      </a>
    </div>`;
}

export function renderSidebar(sidebarActive, simId = null) {
  const sid = simId || localStorage.getItem('prds_last_sim');
  const links = [
    { labelKey: 'sidebar.simulate', page: 'simulate' },
    { labelKey: 'sidebar.monitor', page: 'monitor', needsSim: true },
    { labelKey: 'sidebar.results', page: 'results', needsSim: true },
    { labelKey: 'sidebar.knowledge', page: 'knowledge', needsSim: true },
  ];
  return `
  <aside class="app-sidebar">
    <div class="app-sidebar-brand">
      <a href="#simulate" class="app-sidebar-logo">
        <span class="app-sidebar-logo-mark">${icon('logo', 'icon icon--md')}</span>
        <span class="app-sidebar-logo-text">Odyssey</span>
      </a>
    </div>

    <div class="app-sidebar-section">
      <div class="text-xs text-on-surface-variant leading-snug">${t('sidebar.subtitle')}</div>
      ${sid ? `<div class="text-[10px] font-mono text-outline mt-1.5 truncate" title="${sid}">${sid.slice(0, 8)}</div>` : ''}
    </div>

    <nav class="app-sidebar-nav">
      ${links.map(l => {
        const href = l.needsSim && sid ? `#${l.page}/${sid}` : `#${l.page}`;
        const disabled = l.needsSim && !sid;
        const active = sidebarActive === l.page;
        return `
        <a href="${disabled ? '#' : href}"
           class="sidebar-nav-link ${disabled ? 'sidebar-nav-disabled' : active ? 'sidebar-link-active' : 'sidebar-link-idle'}">
          <span class="nav-icon-wrap">${icon(NAV_ICONS[l.page], 'icon icon--md')}</span>
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
    mainClass = 'ml-[13.5rem] min-h-screen',
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
  if (themeIcon) {
    themeIcon.innerHTML = icon(theme === 'dark' ? 'sun' : 'moon').replace(/^<span[^>]*>|<\/span>$/g, '');
  }
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

export function initReveal() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
  );
  els.forEach((el) => {
    const i = Number(el.style.getPropertyValue('--reveal-i')) || 0;
    const parentDelay = el.closest('.simulate-hero') ? 0 : 0;
    el.style.transitionDelay = `${parentDelay + i * 70}ms`;
    io.observe(el);
  });
}
