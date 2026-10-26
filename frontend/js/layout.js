import { t } from './i18n.js';
import { getPrefs } from './prefs.js';
import { icon } from './icons.js';
import { API, statusLabel, issueLabel } from './api.js';

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function sidebarFooterControls() {
  const prefs = getPrefs();
  const locale = prefs.locale || 'zh';
  const theme = prefs.theme || 'light';
  const themeIconName = theme === 'dark' ? 'sun' : 'moon';

  return `
    <div class="app-sidebar-footer">
      <button type="button" id="sb-locale-btn" class="sidebar-util-btn" title="${t('header.toggleLocale')}" aria-label="${t('header.toggleLocale')}">
        ${icon('globe', 'icon icon--md')}
        <span class="sidebar-util-label">${t('sidebar.language')}</span>
        <span id="sb-locale-label" class="sidebar-util-meta">${locale === 'en' ? 'EN' : '中'}</span>
      </button>
      <button type="button" id="sb-theme-btn" class="sidebar-util-btn" title="${t('header.toggleTheme')}" aria-label="${t('header.toggleTheme')}">
        <span id="sb-theme-icon">${icon(themeIconName, 'icon icon--md')}</span>
        <span class="sidebar-util-label">${t('sidebar.theme')}</span>
        <span class="sidebar-util-meta">${theme === 'dark' ? t('sidebar.themeDark') : t('sidebar.themeLight')}</span>
      </button>
      <button type="button" id="sb-settings-btn" class="sidebar-util-btn" title="${t('nav.settings')}" aria-label="${t('nav.settings')}">
        ${icon('tune', 'icon icon--md')}
        <span class="sidebar-util-label">${t('nav.settings')}</span>
      </button>
    </div>`;
}

function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function historyGroupKey(iso) {
  if (!iso) return 'older';
  const created = new Date(iso);
  if (Number.isNaN(created.getTime())) return 'older';
  const today = startOfDay(new Date());
  const day = startOfDay(created);
  const diffDays = Math.round((today - day) / 86400000);
  if (diffDays <= 0) return 'today';
  if (diffDays === 1) return 'yesterday';
  if (diffDays <= 7) return 'week';
  if (diffDays <= 30) return 'month';
  return 'older';
}

const GROUP_ORDER = ['today', 'yesterday', 'week', 'month', 'older'];

let sidebarRefreshGen = 0;

export function renderSidebar(sidebarActive, opts = {}) {
  const simId = typeof opts === 'string' ? opts : (opts.simId || null);
  const chatSessionId = typeof opts === 'object' ? (opts.chatSessionId || null) : null;
  const activeSimId = simId || null;
  return `
  <aside class="app-sidebar">
    <div class="app-sidebar-brand">
      <a href="#simulate" class="app-sidebar-logo" aria-label="Odyssey">
        <img class="app-sidebar-logo-mark-img" src="./assets/logo-mark.png?v=2" alt="" width="32" height="32" />
        <span class="app-sidebar-logo-text">Odyssey</span>
      </a>
    </div>

    <div class="app-sidebar-section app-sidebar-section--actions">
      <a href="#simulate" class="sb-new-run ${sidebarActive === 'simulate' && !activeSimId ? 'is-active' : ''}">
        <span class="sb-new-run-icon">${icon('compose', 'icon icon--sm')}</span>
        <span class="sb-new-run-label">${t('sidebar.newRun')}</span>
      </a>
      <a href="#chat" class="sb-new-run ${sidebarActive === 'chat' && !chatSessionId ? 'is-active' : ''}">
        <span class="sb-new-run-icon">${icon('bolt', 'icon icon--sm')}</span>
        <span class="sb-new-run-label">${t('sidebar.newChat')}</span>
      </a>
    </div>

    <div class="app-sidebar-nav custom-scrollbar">
      <div id="sb-chat-list" class="sb-chat-list" data-active-chat="${escapeHtml(chatSessionId || '')}">
        <div class="sb-hist-heading">${t('sidebar.chats')}</div>
        <p class="sb-hist-loading">${t('common.loading')}</p>
      </div>
      <div id="sb-history-list" class="sb-history-list" data-active-sim="${escapeHtml(activeSimId || '')}">
        <div class="sb-hist-heading">${t('sidebar.history')}</div>
        <p class="sb-hist-loading">${t('common.loading')}</p>
      </div>
    </div>

    ${sidebarFooterControls()}
  </aside>`;
}

export async function refreshSidebarChats(activeChatId = null, gen = sidebarRefreshGen) {
  const list = document.getElementById('sb-chat-list');
  if (!list) return;
  const nav = list.closest('.app-sidebar-nav');
  const prevScroll = nav ? nav.scrollTop : 0;
  const current = activeChatId ?? list.dataset.activeChat ?? '';
  if (activeChatId != null) list.dataset.activeChat = activeChatId || '';
  const heading = `<div class="sb-hist-heading">${t('sidebar.chats')}</div>`;
  const restoreScroll = () => {
    if (nav) nav.scrollTop = prevScroll;
  };

  try {
    const data = await API.listChatSessions(80);
    if (gen !== sidebarRefreshGen) return;
    const items = data.sessions || [];
    if (!items.length) {
      list.innerHTML = `${heading}<p class="sb-hist-empty">${t('sidebar.chatsEmpty')}</p>`;
      restoreScroll();
      return;
    }

    const groups = {};
    for (const s of items) {
      const key = historyGroupKey(s.updated_at || s.created_at);
      if (!groups[key]) groups[key] = [];
      groups[key].push(s);
    }

    list.innerHTML = heading + GROUP_ORDER.filter((k) => groups[k]?.length).map((key) => `
      <div class="sb-hist-group">
        <div class="sb-hist-group-label">${t(`sidebar.group.${key}`)}</div>
        ${groups[key].map((s) => {
          const title = (s.title || t('sidebar.chatUntitled')).trim() || t('sidebar.chatUntitled');
          const active = current && s.id === current;
          return `
            <div class="sb-hist-row ${active ? 'is-active' : ''}">
              <a href="#chat/${encodeURIComponent(s.id)}"
                 class="sb-hist-item"
                 title="${escapeHtml(title)}">
                ${escapeHtml(title)}
              </a>
              <button type="button"
                class="sb-hist-delete sb-chat-delete"
                data-chat-id="${escapeHtml(s.id)}"
                aria-label="${t('sidebar.deleteChat')}"
                title="${t('sidebar.deleteChat')}">
                ${icon('close', 'icon icon--sm')}
              </button>
            </div>`;
        }).join('')}
      </div>
    `).join('');
    restoreScroll();
  } catch (e) {
    if (gen !== sidebarRefreshGen) return;
    list.innerHTML = `${heading}<p class="sb-hist-empty text-error">${escapeHtml(e.message || String(e))}</p>`;
    restoreScroll();
  }
}

export async function refreshSidebarNav({ simId = null, chatId = null } = {}) {
  const gen = ++sidebarRefreshGen;
  await Promise.all([
    refreshSidebarChats(chatId, gen),
    refreshSidebarHistory(simId, gen),
  ]);
}

/** Update active chat/sim highlight without refetching (avoids sidebar jump). */
export function setSidebarActiveSelection({ chatId = null, simId = null, page = null } = {}) {
  const chatList = document.getElementById('sb-chat-list');
  if (chatList) {
    chatList.dataset.activeChat = chatId || '';
    for (const row of chatList.querySelectorAll('.sb-hist-row')) {
      const href = row.querySelector('a.sb-hist-item')?.getAttribute('href') || '';
      let rowId = null;
      if (href.startsWith('#chat/')) {
        try { rowId = decodeURIComponent(href.slice('#chat/'.length)); } catch { rowId = href.slice('#chat/'.length); }
      }
      row.classList.toggle('is-active', !!chatId && rowId === chatId);
    }
  }

  const histList = document.getElementById('sb-history-list');
  if (histList) {
    histList.dataset.activeSim = simId || '';
    for (const row of histList.querySelectorAll('.sb-hist-row')) {
      const href = row.querySelector('a.sb-hist-item')?.getAttribute('href') || '';
      let rowId = null;
      if (href.startsWith('#simulate/')) {
        try { rowId = decodeURIComponent(href.slice('#simulate/'.length)); } catch { rowId = href.slice('#simulate/'.length); }
      }
      row.classList.toggle('is-active', !!simId && rowId === simId);
    }
  }

  const actions = document.querySelector('.app-sidebar-section--actions');
  if (actions) {
    const currentPage = page
      || (document.getElementById('chat-form') ? 'chat'
        : (document.querySelector('.sim-page:not(.sim-page--chat)') ? 'simulate' : null));
    for (const el of actions.querySelectorAll('a.sb-new-run')) {
      const href = el.getAttribute('href') || '';
      if (href === '#chat') {
        el.classList.toggle('is-active', currentPage === 'chat' && !chatId);
      } else if (href === '#simulate') {
        el.classList.toggle('is-active', currentPage === 'simulate' && !simId);
      }
    }
  }
}

export async function refreshSidebarHistory(activeId = null, gen = sidebarRefreshGen) {
  const list = document.getElementById('sb-history-list');
  if (!list) return;
  const nav = list.closest('.app-sidebar-nav');
  const prevScroll = nav ? nav.scrollTop : 0;
  const current = activeId ?? list.dataset.activeSim ?? '';
  if (activeId != null) list.dataset.activeSim = activeId || '';
  const heading = `<div class="sb-hist-heading">${t('sidebar.history')}</div>`;
  const restoreScroll = () => {
    if (nav) nav.scrollTop = prevScroll;
  };

  try {
    const data = await API.listSimulations(80);
    if (gen !== sidebarRefreshGen) return;
    const items = data.simulations || [];
    if (!items.length) {
      list.innerHTML = `${heading}<p class="sb-hist-empty">${t('sidebar.historyEmpty')}</p>`;
      restoreScroll();
      return;
    }

    const groups = {};
    for (const s of items) {
      const key = historyGroupKey(s.created_at);
      if (!groups[key]) groups[key] = [];
      groups[key].push(s);
    }

    list.innerHTML = heading + GROUP_ORDER.filter((k) => groups[k]?.length).map((key) => `
      <div class="sb-hist-group">
        <div class="sb-hist-group-label">${t(`sidebar.group.${key}`)}</div>
        ${groups[key].map((s) => {
          const title = (s.goal || t('history.untitled')).trim() || t('history.untitled');
          const active = current && s.id === current;
          return `
            <div class="sb-hist-row ${active ? 'is-active' : ''}">
              <a href="#simulate/${encodeURIComponent(s.id)}"
                 class="sb-hist-item"
                 title="${escapeHtml([title, statusLabel(s.status), s.failure ? issueLabel(s.failure) : s.error, ...(s.warnings || []).map(issueLabel)].filter(Boolean).join(' · '))}">
                ${escapeHtml(title)} <span class="text-xs text-outline">· ${escapeHtml(statusLabel(s.status))}</span>
              </a>
              <button type="button"
                class="sb-hist-delete"
                data-sim-id="${escapeHtml(s.id)}"
                aria-label="${t('sidebar.deleteHistory')}"
                title="${t('sidebar.deleteHistory')}">
                ${icon('close', 'icon icon--sm')}
              </button>
            </div>`;
        }).join('')}
      </div>
    `).join('');
    restoreScroll();
  } catch (e) {
    if (gen !== sidebarRefreshGen) return;
    list.innerHTML = `${heading}<p class="sb-hist-empty text-error">${escapeHtml(e.message || String(e))}</p>`;
    restoreScroll();
  }
}

function currentRouteSimId() {
  const parts = (location.hash.slice(1) || 'simulate').split('/').filter(Boolean);
  return parts[0] === 'simulate' ? (parts[1] || null) : null;
}

function currentRouteChatId() {
  const parts = (location.hash.slice(1) || '').split('/').filter(Boolean);
  return parts[0] === 'chat' ? (parts[1] || null) : null;
}

let sidebarHistoryActionsBound = false;

function removeSidebarChatRow(chatId) {
  const list = document.getElementById('sb-chat-list');
  if (!list || !chatId) return;
  const btn = list.querySelector(`.sb-chat-delete[data-chat-id="${CSS.escape(chatId)}"]`);
  const row = btn?.closest('.sb-hist-row');
  const group = row?.closest('.sb-hist-group');
  row?.remove();
  if (group && !group.querySelector('.sb-hist-row')) group.remove();
  if (!list.querySelector('.sb-hist-row')) {
    list.innerHTML = `<div class="sb-hist-heading">${t('sidebar.chats')}</div>`
      + `<p class="sb-hist-empty">${t('sidebar.chatsEmpty')}</p>`;
  }
}

function removeSidebarSimRow(simId) {
  const list = document.getElementById('sb-history-list');
  if (!list || !simId) return;
  const btn = list.querySelector(`.sb-hist-delete:not(.sb-chat-delete)[data-sim-id="${CSS.escape(simId)}"]`);
  const row = btn?.closest('.sb-hist-row');
  const group = row?.closest('.sb-hist-group');
  row?.remove();
  if (group && !group.querySelector('.sb-hist-row')) group.remove();
  if (!list.querySelector('.sb-hist-row')) {
    list.innerHTML = `<div class="sb-hist-heading">${t('sidebar.history')}</div>`
      + `<p class="sb-hist-empty">${t('sidebar.historyEmpty')}</p>`;
  }
}

export function initSidebarHistoryActions() {
  if (sidebarHistoryActionsBound) return;
  sidebarHistoryActionsBound = true;

  document.body.addEventListener('click', async (e) => {
    const chatBtn = e.target.closest('.sb-chat-delete');
    if (chatBtn) {
      e.preventDefault();
      e.stopPropagation();
      const chatId = chatBtn.dataset.chatId;
      if (!chatId) return;
      if (!confirm(t('sidebar.deleteChatConfirm'))) return;
      chatBtn.disabled = true;
      try {
        await API.deleteChatSession(chatId);
        // Remove immediately so the UI does not wait on remount / soft-nav.
        removeSidebarChatRow(chatId);
        const activeChatId = currentRouteChatId();
        const loadedChatId = (document.getElementById('chat-form')?.dataset.chatId || '').trim() || null;
        const deletingActive = chatId === activeChatId || chatId === loadedChatId;
        if (deletingActive) {
          location.hash = '#chat';
          // Soft-nav keeps the sidebar mounted; still refresh list to stay in sync.
          void refreshSidebarNav({ simId: currentRouteSimId(), chatId: null });
          return;
        }
        await refreshSidebarNav({ simId: currentRouteSimId(), chatId: activeChatId });
      } catch (err) {
        alert(t('sidebar.deleteFailed', { msg: err.message || String(err) }));
        chatBtn.disabled = false;
      }
      return;
    }

    const btn = e.target.closest('.sb-hist-delete:not(.sb-chat-delete)');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const simId = btn.dataset.simId;
    if (!simId) return;
    if (!confirm(t('sidebar.deleteConfirm'))) return;

    btn.disabled = true;
    try {
      await API.deleteSimulation(simId);
      removeSidebarSimRow(simId);
      if (localStorage.getItem('prds_last_sim') === simId) {
        localStorage.removeItem('prds_last_sim');
      }
      const activeId = currentRouteSimId();
      const deletingActive = activeId === simId;
      if (deletingActive) {
        location.hash = '#simulate';
        void refreshSidebarNav({ simId: null, chatId: currentRouteChatId() });
        return;
      }
      await refreshSidebarNav({ simId: activeId, chatId: currentRouteChatId() });
    } catch (err) {
      alert(t('sidebar.deleteFailed', { msg: err.message || String(err) }));
      btn.disabled = false;
    }
  });
}

export function pageShell(content, opts = {}) {
  const {
    sidebarActive = null,
    simId = null,
    chatSessionId = null,
    noSidebar = false,
    mainClass = '',
  } = opts;
  const classes = ['app-main', mainClass].filter(Boolean).join(' ');
  return `
    ${noSidebar ? '' : renderSidebar(sidebarActive, { simId, chatSessionId })}
    <main class="${classes}">${content}</main>`;
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
    themeIcon.innerHTML = icon(theme === 'dark' ? 'sun' : 'moon', 'icon icon--md');
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
  // Status badges removed from sidebar UI
}

export function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    els.forEach((el) => el.classList.add('is-visible'));
    return;
  }

  const scrollRoot = document.querySelector('.sim-main') || null;
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        io.unobserve(entry.target);
      });
    },
    {
      root: scrollRoot,
      threshold: 0.1,
      rootMargin: scrollRoot ? '0px 0px -16px 0px' : '0px 0px -32px 0px',
    },
  );
  els.forEach((el, i) => {
    el.style.setProperty('--reveal-delay', `${i * 70}ms`);
    io.observe(el);
  });
  setTimeout(() => {
    els.forEach((el) => el.classList.add('is-visible'));
  }, 900);
}
