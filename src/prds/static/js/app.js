import { initHealthBadge, syncSidebarControls, initReveal } from './layout.js';
import { initAppearance, toggleLocale, toggleTheme } from './theme.js';
import { setDocumentTitle } from './i18n.js';
import { renderSimulate, mountSimulate } from './pages/simulate.js';
import { renderMonitor, mountMonitor, unmountMonitor } from './pages/monitor.js';
import { renderResults, mountResults } from './pages/results.js';
import { renderKnowledge, mountKnowledge } from './pages/knowledge.js';
import { renderModel, mountModel } from './pages/model.js';
import { renderSettings, mountSettings } from './pages/settings.js';

const app = document.getElementById('app');

function parseRoute() {
  const hash = location.hash.slice(1) || 'simulate';
  const [page, id] = hash.split('/').filter(Boolean);
  return { page: page || 'simulate', id: id || null };
}

async function render() {
  unmountMonitor();
  const { page, id } = parseRoute();
  if (id) localStorage.setItem('prds_last_sim', id);

  switch (page) {
    case 'monitor':
      app.innerHTML = renderMonitor(id || localStorage.getItem('prds_last_sim'));
      mountMonitor(id || localStorage.getItem('prds_last_sim'));
      break;
    case 'results':
    case 'agents':
    case 'decisions':
      app.innerHTML = renderResults(id || localStorage.getItem('prds_last_sim'));
      await mountResults(id || localStorage.getItem('prds_last_sim'));
      break;
    case 'knowledge':
      app.innerHTML = renderKnowledge(id);
      await mountKnowledge(id);
      break;
    case 'model':
      app.innerHTML = renderModel();
      await mountModel();
      break;
    case 'settings':
      app.innerHTML = renderSettings();
      mountSettings();
      break;
    case 'simulate':
    default:
      app.innerHTML = renderSimulate();
      mountSimulate();
      break;
  }
  await initHealthBadge();
  setDocumentTitle();
  syncSidebarControls();
  initReveal();
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

async function boot() {
  initAppearance();
  setupGlobalControls();
  if (!location.hash) location.hash = '#simulate';
  else await render();
}

window.addEventListener('hashchange', render);
document.addEventListener('DOMContentLoaded', boot);
