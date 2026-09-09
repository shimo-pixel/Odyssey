import { t } from '../i18n.js';
import { getPrefs, savePrefs, defaultPrefs } from '../prefs.js';
import { icon } from '../icons.js';
import { API } from '../api.js';
import { modelBrandIcon } from '../model-icons.js';

const MODAL_ID = 'settings-modal-root';

function rangeField({ id, name, label, value, min, max, step = 1, suffix = '' }) {
  return `
    <div class="config-chip">
      <div class="flex justify-between items-center mb-1">
        <span class="text-sm font-medium">${label}</span>
        <span class="font-mono font-bold text-primary">
          <span id="${id}-val">${value}</span>${suffix}
        </span>
      </div>
      <input type="range" name="${name}" id="${id}" min="${min}" max="${max}" step="${step}" value="${value}" />
    </div>`;
}

function settingsFormHtml() {
  const prefs = getPrefs();

  return `
    <form id="settings-form" class="settings-modal-body">
      <div class="settings-tabs" role="tablist">
        <button type="button" class="settings-tab is-active" data-tab="model" role="tab" aria-selected="true">${t('settings.tab.model')}</button>
        <button type="button" class="settings-tab" data-tab="params" role="tab" aria-selected="false">${t('settings.tab.params')}</button>
      </div>

      <div class="settings-modal-scroll custom-scrollbar">
      <div class="settings-tab-panel" data-panel="model">
        <section class="glass-panel rounded-lg overflow-hidden">
          <div class="px-5 py-3.5 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('layers', 'icon icon--md text-primary')}${t('settings.modelsAdded')}
            </h2>
            <p class="text-xs text-on-surface-variant mt-1">${t('settings.modelsAddedHint')}</p>
          </div>
          <div id="llm-models-list" class="llm-models-list p-3">
            <p class="text-xs text-on-surface-variant px-2 py-3">${t('common.loading')}</p>
          </div>
        </section>

        <section class="glass-panel rounded-lg overflow-hidden mt-4">
          <div class="px-5 py-3.5 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('link', 'icon icon--md text-primary')}${t('settings.modelConfig')}
            </h2>
            <p class="text-xs text-on-surface-variant mt-1">${t('settings.addModelHint')}</p>
          </div>
          <div class="p-5 space-y-4">
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="block text-sm sm:col-span-2">
                <span class="text-on-surface-variant">${t('settings.modelName')}</span>
                <input type="text" id="llm-name" placeholder="${t('settings.modelNamePlaceholder')}"
                  class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2" />
              </label>
              <label class="block text-sm sm:col-span-2">
                <span class="text-on-surface-variant">${t('settings.apiKey')}</span>
                <input type="password" id="llm-api-key" autocomplete="off"
                  placeholder="${t('settings.apiKeyRequired')}"
                  class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2" />
              </label>
              <label class="block text-sm">
                <span class="text-on-surface-variant">${t('settings.model')}</span>
                <input type="text" id="llm-model" placeholder="deepseek-chat"
                  class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2" />
              </label>
              <label class="block text-sm">
                <span class="text-on-surface-variant">${t('settings.modelAnalysis')}</span>
                <input type="text" id="llm-model-analysis"
                  class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2" />
              </label>
              <label class="block text-sm sm:col-span-2">
                <span class="text-on-surface-variant">${t('settings.apiBase')}</span>
                <input type="text" id="llm-api-base"
                  class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2" />
              </label>
              <label class="block text-sm sm:col-span-2">
                <span class="text-on-surface-variant">${t('settings.provider')}</span>
                <input type="text" id="llm-provider" placeholder="openai"
                  class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2" />
              </label>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <button type="button" id="llm-add-btn" class="btn-start px-5 py-2 rounded-lg text-sm font-medium text-on-primary">
                ${t('settings.addModel')}
              </button>
              <button type="button" id="llm-test-btn" class="px-4 py-2 rounded-lg text-sm font-medium border border-outline-variant text-on-surface hover:bg-surface-container">
                ${t('settings.testConnection')}
              </button>
              <span id="llm-test-status" class="text-xs text-on-surface-variant"></span>
            </div>
          </div>
        </section>
      </div>

      <div class="settings-tab-panel hidden" data-panel="params">
        <section class="glass-panel rounded-lg overflow-hidden">
          <div class="px-5 py-3.5 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('tune', 'icon icon--md text-primary')}${t('settings.defaults')}
            </h2>
          </div>
          <div class="p-5 space-y-5">
            ${rangeField({ id: 'set-agent-range', name: 'defaultAgentCount', label: t('settings.strategyCount'), value: prefs.defaultAgentCount, min: 1, max: 16 })}
            ${rangeField({ id: 'set-max-events-range', name: 'defaultMaxEvents', label: t('settings.eventCount'), value: prefs.defaultMaxEvents, min: 1, max: 40 })}
            <p class="text-xs text-on-surface-variant">${t('settings.countsHint')}</p>
            <label class="flex items-center gap-3 text-sm cursor-pointer">
              <input type="checkbox" name="autoOpenResults" ${prefs.autoOpenResults ? 'checked' : ''} class="rounded accent-primary" />
              ${t('settings.autoResults')}
            </label>
          </div>
        </section>

        <section class="glass-panel rounded-lg overflow-hidden mt-4">
          <div class="px-5 py-3.5 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('bolt', 'icon icon--md text-primary')}${t('settings.algo.engine')}
            </h2>
          </div>
          <div class="p-5 space-y-5">
            ${rangeField({ id: 'set-concurrent-range', name: 'maxConcurrentLlm', label: t('settings.algo.maxConcurrent'), value: prefs.maxConcurrentLlm, min: 1, max: 50 })}
          </div>
        </section>

        <section class="glass-panel rounded-lg overflow-hidden mt-4">
          <div class="px-5 py-3.5 border-b border-outline-variant">
            <h2 class="font-medium text-sm flex items-center gap-2">
              ${icon('storage', 'icon icon--md text-primary')}${t('settings.data')}
            </h2>
          </div>
          <div class="p-5 space-y-3">
            <div class="flex justify-between items-center text-sm">
              <span class="text-on-surface-variant">${t('settings.lastSim')}</span>
              <code id="last-sim-id" class="text-xs font-mono bg-surface-container px-2 py-1 rounded">—</code>
            </div>
            <button type="button" id="clear-sim-btn" class="text-sm text-error hover:underline">${t('settings.clearSim')}</button>
          </div>
        </section>

        <section class="glass-panel rounded-lg p-5 mt-4">
          <h2 class="font-medium text-sm text-on-surface mb-2">${t('settings.about')}</h2>
          <p class="text-sm text-on-surface">Odyssey PRDS v0.1.0</p>
        </section>
      </div>
      </div>

      <div class="settings-modal-footer">
        <button type="button" id="reset-btn" class="px-5 py-2.5 rounded-lg border border-outline-variant text-sm font-medium hover:bg-surface-container">${t('settings.reset')}</button>
        <button type="submit" class="btn-start px-8 py-2.5 rounded-lg text-sm font-medium text-on-primary">${t('settings.save')}</button>
      </div>
    </form>
    <p id="save-toast" class="settings-toast hidden">${t('settings.saved')}</p>`;
}

function modalShellHtml() {
  return `
    <div id="${MODAL_ID}" class="settings-overlay" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title" hidden>
      <div class="settings-modal" role="document">
        <div class="settings-modal-head">
          <div>
            <h1 id="settings-modal-title" class="text-lg font-semibold text-on-surface tracking-tight">${t('settings.title')}</h1>
          </div>
          <button type="button" id="settings-close-btn" class="refine-icon-btn" aria-label="${t('settings.close')}">
            ${icon('close', 'icon icon--md')}
          </button>
        </div>
        ${settingsFormHtml()}
      </div>
    </div>`;
}

function showToast(text) {
  const toast = document.getElementById('save-toast');
  if (!toast) return;
  toast.textContent = text;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 2000);
}

function switchTab(tab) {
  const root = document.getElementById(MODAL_ID);
  if (!root) return;
  const resolved = tab === 'algo' ? 'params' : tab;
  root.querySelectorAll('.settings-tab').forEach((btn) => {
    const active = btn.dataset.tab === resolved;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  root.querySelectorAll('.settings-tab-panel').forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.panel !== resolved);
  });
  const title = document.getElementById('settings-modal-title');
  if (title) title.textContent = t('settings.title');
}

function bindRange(id) {
  const el = document.getElementById(id);
  const val = document.getElementById(`${id}-val`);
  if (!el || !val) return;
  el.addEventListener('input', () => {
    val.textContent = el.value;
  });
}

function setTestStatus(text, ok = null) {
  const el = document.getElementById('llm-test-status');
  if (!el) return;
  el.textContent = text || '';
  el.className = `text-xs ${ok === true ? 'text-success' : ok === false ? 'text-error' : 'text-on-surface-variant'}`;
}

function collectLlmFormPayload({ requireKey = false } = {}) {
  const model = (document.getElementById('llm-model')?.value || '').trim();
  const key = (document.getElementById('llm-api-key')?.value || '').trim();
  if (!model) throw new Error(t('settings.modelRequired'));
  if (requireKey && !key) throw new Error(t('settings.apiKeyNeeded'));
  return {
    name: (document.getElementById('llm-name')?.value || '').trim(),
    model,
    model_analysis: (document.getElementById('llm-model-analysis')?.value || '').trim(),
    api_base: (document.getElementById('llm-api-base')?.value || '').trim(),
    provider: (document.getElementById('llm-provider')?.value || '').trim() || 'openai',
    api_key: key,
  };
}

function clearLlmFormKeys() {
  const key = document.getElementById('llm-api-key');
  if (key) key.value = '';
}

async function renderLlmModelsList() {
  const list = document.getElementById('llm-models-list');
  if (!list) return;
  try {
    const catalog = await API.listLlmModels();
    const models = catalog.models || [];
    const defaultId = catalog.default_model_id || '';
    if (!models.length) {
      list.innerHTML = `<p class="text-xs text-on-surface-variant px-2 py-3">${t('settings.modelsEmpty')}</p>`;
      return;
    }
    list.innerHTML = models.map((m) => {
      const isDefault = m.id === defaultId || m.is_default;
      const label = escapeHtml(m.name || m.model || m.id);
      const meta = escapeHtml([m.model, m.provider].filter(Boolean).join(' · '));
      return `
        <div class="llm-model-row ${isDefault ? 'is-default' : ''}" data-model-id="${escapeHtml(m.id)}">
          <button type="button" class="llm-model-row-main" data-action="set-default" title="${t('settings.setDefault')}">
            ${modelBrandIcon(m.provider, m.model)}
            <span class="llm-model-row-text">
              <span class="llm-model-row-name">${label}${isDefault ? `<span class="llm-model-default-badge">${t('settings.defaultBadge')}</span>` : ''}</span>
              <span class="llm-model-row-meta">${meta}</span>
            </span>
          </button>
          <button type="button" class="llm-model-delete" data-action="delete" title="${t('kb.delete')}" aria-label="${t('kb.delete')}">
            ${icon('close', 'icon icon--sm')}
          </button>
        </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = `<p class="text-xs text-error px-2 py-3">${escapeHtml(e.message || String(e))}</p>`;
  }
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function testLlmConnection() {
  const btn = document.getElementById('llm-test-btn');
  if (btn) btn.disabled = true;
  setTestStatus(t('settings.testing'));
  try {
    const payload = collectLlmFormPayload({ requireKey: false });
    const saved = await API.saveLlmSettings(payload);
    clearLlmFormKeys();
    const health = await API.health();
    const ok = Boolean(saved.configured || health.llm_configured);
    setTestStatus(ok ? t('settings.testOk') : t('settings.testFail'), ok);
    showToast(ok ? t('settings.testOk') : t('settings.testFail'));
    await renderLlmModelsList();
  } catch (e) {
    setTestStatus(e.message || t('settings.testFail'), false);
    showToast(e.message || t('settings.testFail'));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function addLlmModelFromForm() {
  const btn = document.getElementById('llm-add-btn');
  if (btn) btn.disabled = true;
  setTestStatus(t('settings.addingModel'));
  try {
    const payload = collectLlmFormPayload({ requireKey: true });
    await API.addLlmModel(payload);
    clearLlmFormKeys();
    const nameEl = document.getElementById('llm-name');
    if (nameEl) nameEl.value = '';
    setTestStatus(t('settings.modelAdded'), true);
    showToast(t('settings.modelAdded'));
    await renderLlmModelsList();
    window.dispatchEvent(new CustomEvent('prds:llm-models-changed'));
  } catch (e) {
    setTestStatus(e.message || t('settings.addModelFail'), false);
    showToast(e.message || t('settings.addModelFail'));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function onLlmModelsListClick(e) {
  const btn = e.target.closest('[data-action]');
  const row = e.target.closest('[data-model-id]');
  if (!btn || !row) return;
  const id = row.dataset.modelId;
  if (!id) return;
  try {
    if (btn.dataset.action === 'delete') {
      if (!confirm(t('settings.deleteModelConfirm'))) return;
      await API.deleteLlmModel(id);
      showToast(t('settings.modelDeleted'));
    } else if (btn.dataset.action === 'set-default') {
      await API.setDefaultLlmModel(id);
      showToast(t('settings.defaultSet'));
    }
    await renderLlmModelsList();
    window.dispatchEvent(new CustomEvent('prds:llm-models-changed'));
  } catch (err) {
    showToast(err.message || String(err));
  }
}

function collectPrefsFromForm(form) {
  const fd = new FormData(form);
  return {
    defaultAgentCount: Number(fd.get('defaultAgentCount')),
    defaultMaxEvents: Number(fd.get('defaultMaxEvents')),
    autoOpenResults: fd.get('autoOpenResults') === 'on',
    maxConcurrentLlm: Number(fd.get('maxConcurrentLlm')),
  };
}

function bindSettingsHandlers() {
  const root = document.getElementById(MODAL_ID);
  if (!root || root.dataset.bound === '1') return;
  root.dataset.bound = '1';

  const form = document.getElementById('settings-form');
  const lastId = localStorage.getItem('prds_last_sim');
  const lastEl = document.getElementById('last-sim-id');
  if (lastEl) lastEl.textContent = lastId ? `${lastId.slice(0, 13)}…` : t('settings.none');

  root.querySelectorAll('.settings-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  document.getElementById('settings-close-btn')?.addEventListener('click', closeSettingsModal);
  root.addEventListener('click', (e) => {
    if (e.target === root) closeSettingsModal();
  });

  void renderLlmModelsList();

  document.getElementById('llm-models-list')?.addEventListener('click', (e) => {
    void onLlmModelsListClick(e);
  });
  document.getElementById('llm-add-btn')?.addEventListener('click', () => {
    void addLlmModelFromForm();
  });
  document.getElementById('llm-test-btn')?.addEventListener('click', () => {
    void testLlmConnection();
  });

  ['set-agent-range', 'set-max-events-range', 'set-concurrent-range'].forEach(bindRange);

  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    const next = collectPrefsFromForm(form);
    savePrefs(next);
    window.dispatchEvent(new CustomEvent('prds:prefs-changed', { detail: { settings: true } }));
    showToast(t('settings.saved'));
  });

  document.getElementById('reset-btn')?.addEventListener('click', () => {
    savePrefs(defaultPrefs());
    location.reload();
  });

  document.getElementById('clear-sim-btn')?.addEventListener('click', () => {
    localStorage.removeItem('prds_last_sim');
    const el = document.getElementById('last-sim-id');
    if (el) el.textContent = t('settings.none');
  });
}

function onEscape(e) {
  if (e.key === 'Escape') closeSettingsModal();
}

function resolveTab(tab) {
  if (tab === 'prefs' || tab === 'settings' || tab === 'model') return 'model';
  if (tab === 'params' || tab === 'algo') return 'params';
  return 'model';
}

export function openSettingsModal({ tab = 'model' } = {}) {
  let root = document.getElementById(MODAL_ID);
  const locale = getPrefs().locale || 'zh';
  const resolved = resolveTab(tab);

  if (root) {
    root.remove();
    root = null;
  }

  document.body.insertAdjacentHTML('beforeend', modalShellHtml());
  root = document.getElementById(MODAL_ID);
  root.dataset.locale = locale;
  bindSettingsHandlers();

  switchTab(resolved);
  void renderLlmModelsList();
  root.hidden = false;
  document.body.classList.add('settings-modal-open');
  document.removeEventListener('keydown', onEscape);
  document.addEventListener('keydown', onEscape);
}

export function closeSettingsModal() {
  const root = document.getElementById(MODAL_ID);
  if (root) root.hidden = true;
  document.body.classList.remove('settings-modal-open');
  document.removeEventListener('keydown', onEscape);
  const page = (location.hash.slice(1) || '').split('/')[0];
  if (page === 'settings' || page === 'model') {
    const fallback = sessionStorage.getItem('prds_pre_settings_hash') || '#simulate';
    if (location.hash !== fallback) history.replaceState(null, '', fallback);
  }
}

export function isSettingsOpen() {
  const root = document.getElementById(MODAL_ID);
  return Boolean(root && !root.hidden);
}

/** @deprecated */
export function renderSettings() { return ''; }
/** @deprecated */
export function mountSettings() { openSettingsModal(); }

export function applyPrefsToSimulateForm(form) {
  const prefs = getPrefs();
  const agent = form.querySelector('[name="agentCount"]');
  const maxEvents = form.querySelector('[name="maxEvents"]');
  if (agent) {
    agent.value = prefs.defaultAgentCount;
    agent.dispatchEvent(new Event('input'));
  }
  if (maxEvents) {
    maxEvents.value = prefs.defaultMaxEvents;
    maxEvents.dispatchEvent(new Event('input'));
  }
}
