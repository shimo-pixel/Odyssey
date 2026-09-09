import { initHealthBadge, syncSidebarControls, initReveal, refreshSidebarNav, initSidebarHistoryActions, setSidebarActiveSelection } from './layout.js';
import { initAppearance, toggleLocale, toggleTheme } from './theme.js';
import { setDocumentTitle } from './i18n.js';
import { renderSimulate, mountSimulate, unmountSimulate, renderChat, mountChat, unmountChat, switchChatSession } from './pages/simulate.js';
import { unmountHistory } from './pages/history.js';
import { renderKb, mountKb, unmountKb } from './pages/kb.js';
import { openSettingsModal, closeSettingsModal, isSettingsOpen } from './pages/settings.js';

const app = document.getElementById('app');

function parseRoute() {
  const hash = location.hash.slice(1) || 'simulate';
  const [page, id] = hash.split('/').filter(Boolean);
  if (page === 'chat') {
    return { page: 'chat', id: id || null };
  }
  return { page: page || 'simulate', id: id || null };
}

function rememberPreSettingsHash() {
  const hash = location.hash || '#simulate';
  const page = hash.slice(1).split('/')[0];
  if (page !== 'settings' && page !== 'model') {
    sessionStorage.setItem('prds_pre_settings_hash', hash);
  }
}

let activeRoute = { page: null, id: null };

async function render() {
  const { page, id } = parseRoute();

  // Settings / model open as modal — keep underlying page
  if (page === 'settings' || page === 'model') {
    const fallback = sessionStorage.getItem('prds_pre_settings_hash') || '#simulate';
    const tab = (page === 'settings' && (id === 'params' || id === 'algo'))
      ? id
      : 'model';
    if (!app.innerHTML.trim()) {
      sessionStorage.setItem('prds_open_settings_tab', tab);
      location.replace(fallback);
      return;
    }
    openSettingsModal({ tab });
    await initHealthBadge();
    setDocumentTitle();
    syncSidebarControls();
    return;
  }

  if (isSettingsOpen()) closeSettingsModal();
  rememberPreSettingsHash();

  if (id && (page === 'simulate' || page === 'history' || page === 'results' || page === 'monitor')) {
    localStorage.setItem('prds_last_sim', id);
  }

  // Soft-switch between chat sessions: keep sidebar mounted to avoid jump/flicker.
  if (page === 'chat' && activeRoute.page === 'chat' && document.getElementById('chat-form')) {
    const targetId = id || null;
    const loadedId = (document.getElementById('chat-form')?.dataset.chatId || '').trim() || null;
    // Compare against the loaded session, not only activeRoute — replaceState can update
    // the hash without firing hashchange, leaving activeRoute stale.
    if (targetId === loadedId) {
      activeRoute = { page: 'chat', id: targetId };
      setSidebarActiveSelection({ chatId: id, page: 'chat' });
      return;
    }
    activeRoute = { page: 'chat', id: targetId };
    setSidebarActiveSelection({ chatId: id, page: 'chat' });
    await switchChatSession(id);
    setDocumentTitle();
    syncSidebarControls();
    return;
  }

  unmountHistory();
  unmountKb();
  unmountSimulate();
  unmountChat();

  const sidebarCtx = page === 'chat'
    ? { chatId: id, simId: null }
    : page === 'simulate'
      ? { simId: id, chatId: null }
      : { simId: null, chatId: null };

  switch (page) {
    case 'history':
      location.hash = id ? `#simulate/${id}` : '#simulate';
      return;
    case 'monitor':
    case 'results':
    case 'agents':
    case 'decisions':
      location.hash = id ? `#simulate/${id}` : '#simulate';
      return;
    case 'kb':
      app.innerHTML = renderKb(id);
      void refreshSidebarNav(sidebarCtx);
      await mountKb(id);
      break;
    case 'chat':
      app.innerHTML = renderChat(id);
      void refreshSidebarNav(sidebarCtx);
      await mountChat(id);
      break;
    case 'knowledge':
      location.hash = '#kb';
      return;
    case 'simulate':
    default:
      app.innerHTML = renderSimulate(id);
      void refreshSidebarNav(sidebarCtx);
      await mountSimulate(id);
      break;
  }
  activeRoute = { page, id: id || null };
  await initHealthBadge();
  setDocumentTitle();
  syncSidebarControls();
  initReveal();

  const pendingTab = sessionStorage.getItem('prds_open_settings_tab');
  if (pendingTab) {
    sessionStorage.removeItem('prds_open_settings_tab');
    openSettingsModal({ tab: pendingTab });
  }
}

function setupGlobalControls() {
  document.body.addEventListener('click', (e) => {
    if (e.target.closest('#sb-locale-btn')) {
      e.preventDefault();
      toggleLocale();
      return;
    }
    if (e.target.closest('#sb-theme-btn')) {
      e.preventDefault();
      toggleTheme();
      return;
    }
    if (e.target.closest('#sb-settings-btn')) {
      e.preventDefault();
      rememberPreSettingsHash();
      openSettingsModal({ tab: 'prefs' });
    }
  });

  window.addEventListener('prds:prefs-changed', (e) => {
    if (e.detail?.themeOnly) {
      syncSidebarControls();
      return;
    }
    render();
  });
}

initAppearance();
setupGlobalControls();
initSidebarHistoryActions();
window.addEventListener('hashchange', render);
render();
