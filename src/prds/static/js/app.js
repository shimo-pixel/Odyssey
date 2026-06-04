import { initHealthBadge } from './layout.js';
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
}

window.addEventListener('hashchange', render);
document.addEventListener('DOMContentLoaded', () => {
  if (!location.hash) location.hash = '#simulate';
  else render();
});
