import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import { getPrefs, savePrefs, defaultPrefs } from '../prefs.js';
import { icon } from '../icons.js';

export function renderSettings() {
  const prefs = getPrefs();

  return pageShell(`
    <div class="p-8 lg:p-12 max-w-3xl mx-auto pb-20">
      <header class="mb-10">
        <h1 class="text-2xl font-semibold text-on-surface tracking-tight">${t('settings.title')}</h1>
        <p class="text-sm text-on-surface-variant mt-2">${t('settings.subtitle')}</p>
      </header>

      <form id="settings-form" class="space-y-6">
        <section class="glass-panel rounded-lg overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('link', 'icon icon--md text-primary')}${t('settings.connection')}
            </h2>
          </div>
          <div class="p-6 space-y-4">
            <div id="conn-status" class="flex items-center justify-between p-4 rounded-lg bg-surface-container-low">
              <div><p class="text-sm font-medium">${t('settings.llm')}</p><p class="text-xs text-on-surface-variant" id="conn-detail">${t('settings.checking')}</p></div>
              <span id="conn-badge" class="text-xs font-medium px-2 py-1 rounded-md bg-surface-variant">—</span>
            </div>
            <p class="text-xs text-on-surface-variant">${t('settings.apiHint')}</p>
          </div>
        </section>

        <section class="glass-panel rounded-lg overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('tune', 'icon icon--md text-primary')}${t('settings.defaults')}
            </h2>
          </div>
          <div class="p-6 space-y-5">
            <div class="config-chip">
              <div class="flex justify-between"><span class="text-sm font-medium">${t('settings.agentCount')}</span><span id="set-agent-val" class="font-mono font-bold text-primary">${prefs.defaultAgentCount}</span></div>
              <input type="range" name="defaultAgentCount" min="5" max="100" value="${prefs.defaultAgentCount}" id="set-agent-range"/>
            </div>
            <div class="config-chip">
              <div class="flex justify-between"><span class="text-sm font-medium">${t('settings.maxEvents')}</span><span id="set-max-events-val" class="font-mono font-bold text-primary">${prefs.defaultMaxEvents}</span></div>
              <input type="range" name="defaultMaxEvents" min="3" max="24" value="${prefs.defaultMaxEvents}" id="set-max-events-range"/>
            </div>
            <label class="flex items-center gap-3 text-sm cursor-pointer">
              <input type="checkbox" name="autoOpenResults" ${prefs.autoOpenResults ? 'checked' : ''} class="rounded accent-primary"/>
              ${t('settings.autoResults')}
            </label>
          </div>
        </section>

        <section class="glass-panel rounded-lg overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('storage', 'icon icon--md text-primary')}${t('settings.data')}
            </h2>
          </div>
          <div class="p-6 space-y-3">
            <div class="flex justify-between items-center text-sm">
              <span class="text-on-surface-variant">${t('settings.lastSim')}</span>
              <code id="last-sim-id" class="text-xs font-mono bg-surface-container px-2 py-1 rounded">—</code>
            </div>
            <button type="button" id="clear-sim-btn" class="text-sm text-error hover:underline">${t('settings.clearSim')}</button>
          </div>
        </section>

        <section class="glass-panel rounded-lg p-6">
          <h2 class="font-medium text-sm text-on-surface mb-2">${t('settings.about')}</h2>
          <p class="text-sm text-on-surface">Odyssey PRDS v0.1.0</p>
          <p class="text-xs text-on-surface-variant mt-1">${t('settings.aboutDesc')}</p>
        </section>

        <div class="flex justify-end gap-3">
          <button type="button" id="reset-btn" class="px-5 py-2.5 rounded-lg border border-outline-variant text-sm font-medium hover:bg-surface-container">${t('settings.reset')}</button>
          <button type="submit" class="btn-start px-8 py-2.5 rounded-lg text-sm font-medium text-on-primary">${t('settings.save')}</button>
        </div>
      </form>
      <p id="save-toast" class="fixed bottom-6 right-6 hidden text-white text-sm font-medium px-4 py-2.5 rounded-lg shadow-sm" style="background:var(--success)">${t('settings.saved')}</p>
    </div>
  `, { sidebarActive: 'settings', mainClass: 'ml-[13.5rem] min-h-screen bg-background' });
}

export function mountSettings() {
  const form = document.getElementById('settings-form');
  const prefs = getPrefs();
  const lastId = localStorage.getItem('prds_last_sim');
  document.getElementById('last-sim-id').textContent = lastId ? lastId.slice(0, 13) + '…' : t('settings.none');

  fetch('/health').then(r => r.json()).then(h => {
    const badge = document.getElementById('conn-badge');
    const detail = document.getElementById('conn-detail');
    if (h.llm_configured) {
      badge.textContent = t('settings.connected');
      badge.className = 'text-xs font-medium px-2 py-1 rounded-md g-chip g-chip-green';
      detail.textContent = t('settings.apiConfigured');
    } else {
      badge.textContent = t('settings.notConfigured');
      badge.className = 'text-xs font-medium px-2 py-1 rounded-md g-chip g-chip-blue';
      detail.textContent = t('settings.noApiKey');
    }
  }).catch(() => {});

  document.getElementById('set-agent-range')?.addEventListener('input', e => {
    document.getElementById('set-agent-val').textContent = e.target.value;
  });
  document.getElementById('set-max-events-range')?.addEventListener('input', e => {
    document.getElementById('set-max-events-val').textContent = e.target.value;
  });

  document.getElementById('clear-sim-btn')?.addEventListener('click', () => {
    localStorage.removeItem('prds_last_sim');
    document.getElementById('last-sim-id').textContent = t('settings.none');
  });

  document.getElementById('reset-btn')?.addEventListener('click', () => {
    savePrefs(defaultPrefs());
    location.reload();
  });

  form?.addEventListener('submit', e => {
    e.preventDefault();
    const fd = new FormData(form);
    savePrefs({
      defaultAgentCount: Number(fd.get('defaultAgentCount')),
      defaultMaxEvents: Number(fd.get('defaultMaxEvents')),
      autoOpenResults: fd.get('autoOpenResults') === 'on',
      locale: prefs.locale || 'zh',
      theme: prefs.theme || 'light',
    });
    const toast = document.getElementById('save-toast');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2000);
  });
}

export { getPrefs, savePrefs, defaultPrefs } from '../prefs.js';

export function applyPrefsToSimulateForm(form) {
  const prefs = getPrefs();
  const agent = form.querySelector('[name="agentCount"]');
  const maxEvents = form.querySelector('[name="maxEvents"]');
  if (agent) { agent.value = prefs.defaultAgentCount; agent.dispatchEvent(new Event('input')); }
  if (maxEvents) { maxEvents.value = prefs.defaultMaxEvents; maxEvents.dispatchEvent(new Event('input')); }
}
