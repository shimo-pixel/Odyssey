import { API, buildPayload, getPhaseSteps, statusLabel, phaseLabel, TERMINAL_STATUSES, issueLabel } from '../api.js';
import { pageShell, refreshSidebarNav } from '../layout.js';
import { icon, spinner } from '../icons.js';
import { t } from '../i18n.js';
import { getPrefs, savePrefs } from '../prefs.js';
import { mountResults } from './results.js';
import { modelBrandIcon } from '../model-icons.js';
import { ensureChatRenderers, formatChatHtml } from '../math-render.js';

const PIPELINE_TONES = ['blue', 'green', 'violet', 'teal', 'amber', 'coral'];
const PIPELINE_ICONS = ['brain', 'schema', 'knowledge', 'users', 'merge', 'insights'];
const PIPELINE_DESC_KEYS = ['analysis', 'goal', 'ontology', 'knowledge', 'spawn', 'converge'];

/** @type {Set<string>} */
let selectedKbIds = new Set();
/** @type {'simulate' | 'research' | 'answer'} */
let activeMode = 'simulate';
/** @type {{ id: string, name: string } | null} */
let kbDrillCategory = null;
/** @type {Array<{id:string,name?:string,model?:string,provider?:string,is_default?:boolean}>} */
let modelCatalog = [];
let modelMenuOutsideHandler = null;
let statusStop = null;
let runLoadGen = 0;
let runActionBusy = false;
let runAbort = null;
let menuOutsideHandler = null;
let chatSessionId = null;
/** @type {Array<{role:string,content:string,model?:string}>} */
let chatMessages = [];
let chatLoadGen = 0;

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function progressBarHtml(pct) {
  const w = Math.max(0, Math.min(100, Number(pct) || 0));
  return `
    <div class="h-1.5 bg-surface-container rounded-full overflow-hidden mt-3">
      <div class="h-full rounded-full" style="width:${w}%;background:linear-gradient(90deg,var(--tone-blue),var(--tone-green))"></div>
    </div>`;
}

function kbPanel() {
  return `
    <aside class="sim-kb-panel custom-scrollbar">
      <header class="sim-kb-head">
        <div class="sim-kb-head-top">
          <h2 class="sim-kb-title">${t('sim.kbSelect')}</h2>
        </div>
        <p class="sim-kb-hint">${t('sim.kbSelectHint')}</p>
        <a href="#kb" class="sim-kb-manage">
          <span>${t('sim.kbOpen')}</span>
          ${icon('arrowRight', 'icon icon--sm')}
        </a>
      </header>

      <div class="sim-kb-body">
        <div id="kb-select-list" class="sim-kb-list">
          <p class="sim-kb-empty">${t('common.loading')}</p>
        </div>
      </div>

      <footer class="sim-kb-foot">
        <div class="sim-kb-ready-row">
          <span class="sim-kb-ready-label">${t('sim.readiness')}</span>
          <span class="sim-kb-ready-meta" id="ready-label">${t('sim.ready.empty')}</span>
        </div>
        <div class="sim-kb-ready-track">
          <div class="sim-kb-ready-bar" id="ready-bar"></div>
        </div>
      </footer>
    </aside>`;
}

function dismissBtn(id) {
  return `<button type="button" class="sim-dismiss-btn" data-dismiss="${id}" aria-label="${t('common.close')}">${icon('close', 'icon icon--sm')}</button>`;
}

function modeLabelKey(mode) {
  if (mode === 'research') return 'sim.mode.research';
  if (mode === 'answer') return 'sim.mode.answer';
  return 'sim.mode.simulate';
}

function modePlaceholder(mode) {
  if (mode === 'research') return t('sim.goal.placeholderResearch');
  if (mode === 'answer') return t('sim.goal.placeholderAnswer');
  return t('sim.goal.placeholder');
}

function startBtnLabel() {
  if (activeMode === 'research') return t('sim.startResearch');
  if (activeMode === 'answer') return t('sim.startAnswer');
  return t('sim.start');
}

function chatComposerPanel() {
  return `
    <div class="sim-composer sim-composer--chat">
      <div class="sim-composer-inner sim-composer-inner--chat">
        <div class="sim-composer-body">
          <textarea id="goal" name="goal" data-field="goal" rows="3"
            class="sim-composer-textarea sim-composer-textarea--chat active"
            placeholder="${escapeHtml(t('sim.chat.placeholder'))}"></textarea>
        </div>
        <div class="sim-composer-bar sim-composer-bar--chat">
          <div class="sim-composer-bar-left sim-composer-bar-left--chat"></div>
          <div class="sim-composer-bar-right">
            <div class="sim-picker-wrap sim-model-picker">
              <button type="button" id="sim-model-btn" class="sim-model-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="sim-model-menu" title="${t('sim.modelSelect')}">
                <span id="sim-model-label" class="sim-model-trigger-label">${t('sim.modelEmpty')}</span>
                <svg class="sim-model-chevron" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <path d="M3 8l3-3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
              </button>
              <div id="sim-model-menu" class="sim-picker-menu sim-model-menu custom-scrollbar" hidden role="listbox" aria-label="${t('sim.modelSelect')}"></div>
              <input type="hidden" id="sim-model-select" value="" />
            </div>
            <button type="submit" id="start-btn" class="sim-run-btn" disabled aria-label="${escapeHtml(startBtnLabel())}" title="${escapeHtml(startBtnLabel())}">
              ${startBtnHtml(false)}
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

function chatEmptyHeroHtml() {
  return `
    <div id="chat-empty-hero" class="chat-empty-hero">
      <img class="chat-empty-brand" src="./assets/logo-wordmark.png?v=3" alt="Odyssey" />
    </div>`;
}

function updateChatLayoutState() {
  const form = document.getElementById('chat-form');
  if (!form) return;
  const isEmpty = !chatMessages.length;
  form.classList.toggle('is-empty', isEmpty);
  form.classList.toggle('is-active', !isEmpty);
}

function composerPanel() {
  return `
    <div class="sim-composer">
      <div class="sim-composer-inner">
        <div class="sim-composer-body">
          <textarea id="goal" name="goal" data-field="goal" rows="4"
            class="sim-composer-textarea active"
            placeholder="${escapeHtml(modePlaceholder(activeMode))}"></textarea>
          <div id="sim-upload-list" class="sim-upload-list hidden"></div>
        </div>
        <div class="sim-composer-bar">
          <div class="sim-composer-bar-left">
            <div class="sim-plus-wrap">
              <button type="button" id="sim-plus-btn" class="sim-icon-btn" title="${t('sim.modeMenu')}" aria-label="${t('sim.modeMenu')}" aria-expanded="false" aria-haspopup="true">
                ${icon('add', 'icon icon--md')}
              </button>
              <div id="sim-plus-menu" class="sim-plus-menu hidden" role="menu">
                <button type="button" class="sim-plus-item" data-action="upload" role="menuitem">
                  ${icon('storage', 'icon icon--sm')}<span>${t('sim.mode.upload')}</span>
                </button>
                <button type="button" class="sim-plus-item" data-mode="simulate" role="menuitem">
                  ${icon('simulate', 'icon icon--sm')}<span>${t('sim.mode.simulate')}</span>
                </button>
                <button type="button" class="sim-plus-item" data-mode="research" role="menuitem">
                  ${icon('search', 'icon icon--sm')}<span>${t('sim.mode.research')}</span>
                </button>
                <button type="button" class="sim-plus-item" data-mode="answer" role="menuitem">
                  ${icon('bolt', 'icon icon--sm')}<span>${t('sim.mode.answer')}</span>
                </button>
              </div>
            </div>
            <input id="sim-file-input" type="file" class="hidden" multiple />
            <span id="sim-mode-chip" class="sim-mode-chip">${t(modeLabelKey(activeMode))}</span>
            <span id="sim-upload-msg" class="text-[11px] text-on-surface-variant"></span>
          </div>
          <div class="sim-composer-bar-right">
            <div class="sim-picker-wrap sim-model-picker">
              <button type="button" id="sim-model-btn" class="sim-model-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="sim-model-menu" title="${t('sim.modelSelect')}">
                <span id="sim-model-label" class="sim-model-trigger-label">${t('sim.modelEmpty')}</span>
                <svg class="sim-model-chevron" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <path d="M3 8l3-3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
              </button>
              <div id="sim-model-menu" class="sim-picker-menu sim-model-menu custom-scrollbar" hidden role="listbox" aria-label="${t('sim.modelSelect')}"></div>
              <input type="hidden" id="sim-model-select" value="" />
            </div>
            <button type="submit" id="start-btn" class="sim-run-btn" disabled aria-label="${escapeHtml(startBtnLabel())}" title="${escapeHtml(startBtnLabel())}">
              ${startBtnHtml(false)}
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

function emptyWorkspaceHtml() {
  const phaseSteps = getPhaseSteps();
  return `
    <div class="sim-main-inner" id="sim-workspace-empty">
      <section class="simulate-hero reveal" data-sim-panel="hero">
        ${dismissBtn('hero')}
        <h1 class="hero-title">${t('sim.hero.title')}</h1>
        <p class="hero-desc">${t('sim.hero.desc')}</p>
        ${heroHighlights()}
      </section>

      <section class="mt-8 reveal" data-sim-panel="pipeline">
        <div class="sim-panel-head">
          <h2 class="text-ui-sm font-medium text-on-surface">${t('sim.pipeline')}</h2>
          ${dismissBtn('pipeline')}
        </div>
        <div class="sim-pipeline-grid">
          ${phaseSteps.map((s, i) => pipelineCard(s.label, i)).join('')}
        </div>
      </section>

      <section class="mt-6 reveal" data-sim-panel="tip">
        <div class="sim-tip-card">
          ${dismissBtn('tip')}
          <p class="sim-tip-body">${t('sim.tip.body')}</p>
        </div>
      </section>
    </div>`;
}

export function renderSimulate(simId = null) {
  return pageShell(`
    <form id="sim-form" class="sim-page" data-sim-id="${escapeHtml(simId || '')}">
      ${kbPanel()}

      <div class="sim-main custom-scrollbar">
        <div id="sim-workspace" class="${simId ? 'sim-workspace-run' : ''}">
          ${simId
            ? `<div class="flex items-center justify-center py-24"><div class="animate-pulse text-primary font-bold">${t('results.loading')}</div></div>`
            : emptyWorkspaceHtml()}
        </div>
      </div>

      ${composerPanel()}
    </form>
  `, { sidebarActive: 'simulate', simId });
}

const HIGHLIGHT_META = [
  { tone: 'blue', icon: 'layers', titleKey: 'sim.hero.hl1.title', descKey: 'sim.hero.hl1.desc' },
  { tone: 'green', icon: 'bolt', titleKey: 'sim.hero.hl2.title', descKey: 'sim.hero.hl2.desc' },
  { tone: 'amber', icon: 'insights', titleKey: 'sim.hero.hl3.title', descKey: 'sim.hero.hl3.desc' },
];

function heroHighlights() {
  return `
    <div class="hero-highlights">
      ${HIGHLIGHT_META.map((h, i) => `
        <div class="hero-highlight" data-tone="${h.tone}" style="--reveal-i:${i}">
          <span class="hero-highlight-icon">${icon(h.icon, 'icon icon--sm')}</span>
          <div>
            <div class="hero-highlight-title">${t(h.titleKey)}</div>
            <div class="hero-highlight-desc">${t(h.descKey)}</div>
          </div>
        </div>`).join('')}
    </div>`;
}

function pipelineCard(label, index) {
  const descKey = PIPELINE_DESC_KEYS[index] || 'analysis';
  const tone = PIPELINE_TONES[index] || 'blue';
  const ic = PIPELINE_ICONS[index] || 'layers';
  const num = String(index + 1).padStart(2, '0');
  return `
    <div class="sim-pipeline-step" data-tone="${tone}" style="--reveal-i:${index}">
      <span class="sim-pipeline-icon">${icon(ic, 'icon icon--sm')}</span>
      <div class="sim-pipeline-body">
        <div class="flex items-center gap-2 mb-0.5">
          <span class="sim-pipeline-num">${num}</span>
          <h3 class="sim-pipeline-title">${label}</h3>
        </div>
        <p class="sim-pipeline-desc">${t(`phaseStep.${descKey}.desc`)}</p>
      </div>
    </div>`;
}

function formatDocSize(n) {
  const num = Number(n) || 0;
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
  return `${(num / (1024 * 1024)).toFixed(1)} MB`;
}

async function loadKbCategories() {
  const list = document.getElementById('kb-select-list');
  if (!list) return;
  kbDrillCategory = null;
  try {
    const cats = await API.listKbCategories();
    if (!cats.length) {
      list.innerHTML = `<p class="sim-kb-empty">${t('sim.kbEmpty')}</p>`;
      return;
    }
    list.innerHTML = cats.map((c) => {
      const id = escapeHtml(c.id);
      const checked = selectedKbIds.has(c.id) ? 'checked' : '';
      return `
        <div class="sim-kb-item">
          <input type="checkbox" class="kb-cat-check sim-kb-check" value="${id}" ${checked} aria-label="${escapeHtml(c.name || c.id)}" />
          <button type="button" class="sim-kb-item-body sim-kb-cat-open" data-cat-id="${id}" data-cat-name="${escapeHtml(c.name || c.id)}">
            <span class="sim-kb-item-name">${escapeHtml(c.name || c.id)}</span>
            <span class="sim-kb-item-meta">${t('kb.docCount', { n: c.document_count || 0 })}</span>
          </button>
        </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = `<p class="sim-kb-empty sim-kb-empty--error">${escapeHtml(e.message || String(e))}</p>`;
  }
}

async function loadKbDocuments(catId, catName) {
  const list = document.getElementById('kb-select-list');
  if (!list) return;
  kbDrillCategory = { id: catId, name: catName || catId };
  list.innerHTML = `<p class="sim-kb-empty">${t('common.loading')}</p>`;
  try {
    const docs = await API.listKbDocuments(catId);
    const head = `
      <button type="button" class="sim-kb-back" id="kb-drill-back">${t('sim.kbBack')}</button>
      <p class="sim-kb-item-meta px-1 mb-2">${escapeHtml(catName || catId)}</p>`;
    if (!docs.length) {
      list.innerHTML = `${head}<p class="sim-kb-empty">${t('sim.kbDocsEmpty')}</p>`;
      return;
    }
    list.innerHTML = head + docs.map((d) => `
      <div class="sim-kb-doc-row">
        <span class="sim-kb-doc-name">${escapeHtml(d.filename || d.file_name || d.id)}</span>
        <span class="sim-kb-item-meta">${escapeHtml(d.status || '—')} · ${formatDocSize(d.size)}</span>
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `
      <button type="button" class="sim-kb-back" id="kb-drill-back">${t('sim.kbBack')}</button>
      <p class="sim-kb-empty sim-kb-empty--error">${escapeHtml(e.message || String(e))}</p>`;
  }
}

async function refreshModelSelect() {
  const hidden = document.getElementById('sim-model-select');
  const label = document.getElementById('sim-model-label');
  const menu = document.getElementById('sim-model-menu');
  if (!hidden || !label || !menu) return;

  const prefs = getPrefs();
  try {
    const catalog = await API.listLlmModels();
    modelCatalog = catalog.models || [];
    const preferred = prefs.selectedModelId || catalog.default_model_id || '';
    let selectedId = preferred;

    if (!modelCatalog.length) {
      hidden.value = '';
      label.textContent = t('sim.modelEmpty');
      menu.innerHTML = `<p class="sim-model-menu-empty">${t('sim.modelEmpty')}</p>`;
      return;
    }

    if (selectedId && !modelCatalog.some((m) => m.id === selectedId)) {
      selectedId = catalog.default_model_id || modelCatalog[0].id;
    }
    if (!selectedId) {
      selectedId = catalog.default_model_id || modelCatalog[0].id;
    }

    hidden.value = selectedId;
    if (selectedId !== prefs.selectedModelId) {
      savePrefs({ selectedModelId: selectedId });
    }

    const current = modelCatalog.find((m) => m.id === selectedId);
    label.textContent = current?.name || current?.model || t('sim.modelSelect');

    menu.innerHTML = modelCatalog.map((m) => {
      const active = m.id === selectedId;
      const title = escapeHtml(m.name || m.model || m.id);
      const desc = escapeHtml([m.model, m.provider].filter(Boolean).join(' · '));
      return `
        <button type="button" class="sim-picker-item sim-model-item${active ? ' active' : ''}" role="option" aria-selected="${active ? 'true' : 'false'}" data-model-id="${escapeHtml(m.id)}">
          <span class="sim-picker-icon">${modelBrandIcon(m.provider, m.model, 'model-brand-icon')}</span>
          <span class="sim-picker-text">
            <span class="sim-picker-title">${title}</span>
            <span class="sim-picker-desc">${desc}</span>
          </span>
          <span class="sim-picker-check" aria-hidden="true">✓</span>
        </button>`;
    }).join('');
  } catch {
    modelCatalog = [];
    hidden.value = '';
    label.textContent = t('sim.modelEmpty');
    menu.innerHTML = `<p class="sim-model-menu-empty">${t('sim.modelEmpty')}</p>`;
  }
}

function getSelectedModelId() {
  return document.getElementById('sim-model-select')?.value || getPrefs().selectedModelId || '';
}

function selectModel(modelId) {
  const hidden = document.getElementById('sim-model-select');
  const label = document.getElementById('sim-model-label');
  const menu = document.getElementById('sim-model-menu');
  if (!hidden || !label) return;

  hidden.value = modelId || '';
  savePrefs({ selectedModelId: modelId || '' });

  const current = modelCatalog.find((m) => m.id === modelId);
  label.textContent = current?.name || current?.model || t('sim.modelEmpty');

  menu?.querySelectorAll('.sim-model-item').forEach((item) => {
    const active = item.dataset.modelId === modelId;
    item.classList.toggle('active', active);
    item.setAttribute('aria-selected', active ? 'true' : 'false');
  });

  closeModelMenu();
}

function closeModelMenu() {
  const menu = document.getElementById('sim-model-menu');
  const btn = document.getElementById('sim-model-btn');
  menu?.setAttribute('hidden', '');
  btn?.setAttribute('aria-expanded', 'false');
  if (modelMenuOutsideHandler) {
    document.removeEventListener('click', modelMenuOutsideHandler);
    modelMenuOutsideHandler = null;
  }
}

function openModelMenu() {
  const menu = document.getElementById('sim-model-menu');
  const btn = document.getElementById('sim-model-btn');
  if (!menu || !btn) return;
  closePlusMenu();
  menu.removeAttribute('hidden');
  btn.setAttribute('aria-expanded', 'true');
  modelMenuOutsideHandler = (e) => {
    if (e.target.closest('.sim-model-picker')) return;
    closeModelMenu();
  };
  setTimeout(() => document.addEventListener('click', modelMenuOutsideHandler), 0);
}

function chatTurnHtml(msg, index, { streaming = false } = {}) {
  if (msg.role === 'user') {
    return `
      <div class="sim-chat-turn sim-chat-turn--user">
        <div class="sim-chat-bubble sim-chat-bubble--user">${formatChatHtml(msg.content)}</div>
        <div class="sim-chat-actions">
          <button type="button" class="sim-chat-action" data-copy="${index}" title="${t('sim.chat.copy')}" aria-label="${t('sim.chat.copy')}">
            ${icon('note', 'icon icon--sm')}
          </button>
        </div>
      </div>`;
  }
  if (!msg.content && streaming) return '';
  return `
    <div class="sim-chat-turn sim-chat-turn--assistant" data-stream-turn="${streaming ? '1' : '0'}">
      <div class="sim-chat-bubble sim-chat-bubble--assistant" data-stream-bubble="${streaming ? '1' : '0'}">${formatChatHtml(msg.content)}</div>
      <div class="sim-chat-actions">
        <button type="button" class="sim-chat-action" data-copy="${index}" title="${t('sim.chat.copy')}" aria-label="${t('sim.chat.copy')}">
          ${icon('note', 'icon icon--sm')}
        </button>
      </div>
      ${msg.model ? `<div class="sim-chat-meta">${escapeHtml(msg.model)}</div>` : ''}
    </div>`;
}

function updateStreamingBubble(content) {
  const bubble = document.querySelector('[data-stream-bubble="1"]');
  if (!bubble) return;
  bubble.innerHTML = formatChatHtml(content);
  scrollChatToBottom();
}

function renderChatThread({ streaming = false, error = null } = {}) {
  const thread = document.getElementById('sim-chat-thread');
  if (!thread) return;
  updateChatLayoutState();
  if (!chatMessages.length && !error) {
    thread.innerHTML = '';
    return;
  }
  const paint = () => {
    if (document.getElementById('sim-chat-thread') !== thread) return;
    let html = chatMessages.map((m, i) => {
      const isStreamingAssistant = streaming && i === chatMessages.length - 1 && m.role === 'assistant';
      return chatTurnHtml(m, i, { streaming: isStreamingAssistant });
    }).join('');
    if (error) {
      html += `<p class="sim-chat-error">${escapeHtml(error)}</p>`;
    }
    thread.innerHTML = html;
    scrollChatToBottom();
  };
  paint();
  if (typeof window !== 'undefined' && !(window.katex && window.marked)) {
    void ensureChatRenderers()
      .then(() => paint())
      .catch(() => {});
  }
}

function scrollChatToBottom() {
  const main = document.querySelector('.sim-main--chat') || document.querySelector('.sim-main');
  if (main) {
    requestAnimationFrame(() => {
      main.scrollTop = main.scrollHeight;
    });
  }
}

async function loadChatSession(sessionId, { loadGen = null } = {}) {
  if (!sessionId) {
    chatMessages = [];
    chatSessionId = null;
    renderChatThread();
    return;
  }
  const data = await API.getChatSession(sessionId);
  if (loadGen != null && loadGen !== chatLoadGen) return;
  chatSessionId = data.id;
  chatMessages = (data.messages || []).map((m) => ({
    role: m.role,
    content: m.content,
    model: m.model,
  }));
  if (data.model_id) {
    savePrefs({ selectedModelId: data.model_id });
    await refreshModelSelect();
    if (loadGen != null && loadGen !== chatLoadGen) return;
  }
  renderChatThread();
}

async function runQuickAnswer(message) {
  void ensureChatRenderers().catch(() => {});
  const modelId = getSelectedModelId();
  chatMessages.push({ role: 'user', content: message });
  renderChatThread();
  const goal = document.getElementById('goal');
  if (goal) goal.value = '';
  updateComposerState();

  let assistantIdx = -1;
  let streamModel = null;

  const finalizeSession = (sessionId) => {
    chatSessionId = sessionId;
    const form = document.getElementById('chat-form');
    if (form) form.dataset.chatId = chatSessionId;
    if (location.hash !== `#chat/${encodeURIComponent(chatSessionId)}`) {
      history.replaceState(null, '', `#chat/${encodeURIComponent(chatSessionId)}`);
    }
    void refreshSidebarNav({ chatId: chatSessionId, simId: null });
  };

  try {
    await API.chatAnswerStream({
      message,
      model_id: modelId || null,
      session_id: chatSessionId,
      onMeta: (event) => {
        if (event.session_id) finalizeSession(event.session_id);
        if (event.model) streamModel = event.model;
      },
      onDelta: (chunk) => {
        if (!chunk) return;
        if (assistantIdx === -1) {
          chatMessages.push({ role: 'assistant', content: chunk, model: streamModel });
          assistantIdx = chatMessages.length - 1;
          renderChatThread({ streaming: true });
          return;
        }
        chatMessages[assistantIdx].content += chunk;
        updateStreamingBubble(chatMessages[assistantIdx].content);
      },
      onDone: (event) => {
        if (assistantIdx === -1) {
          chatMessages.push({
            role: 'assistant',
            content: event.answer || '',
            model: event.model || streamModel,
          });
        } else {
          chatMessages[assistantIdx].content = event.answer || chatMessages[assistantIdx].content;
          if (event.model) chatMessages[assistantIdx].model = event.model;
        }
        if (event.session_id) finalizeSession(event.session_id);
        renderChatThread();
      },
      onError: (err) => {
        if (assistantIdx !== -1) chatMessages.pop();
        renderChatThread({ error: t('sim.answer.failed', { msg: err.message || String(err) }) });
      },
    });
  } catch (e) {
    if (assistantIdx !== -1) chatMessages.pop();
    renderChatThread({ error: t('sim.answer.failed', { msg: e.message || String(e) }) });
  }
}

function bindComposerHandlers(form, { onSubmit } = {}) {
  form.addEventListener('click', (e) => {
    const copyBtn = e.target.closest('[data-copy]');
    if (copyBtn) {
      e.preventDefault();
      const idx = Number(copyBtn.dataset.copy);
      const msg = chatMessages[idx];
      if (msg?.content && navigator.clipboard?.writeText) {
        void navigator.clipboard.writeText(msg.content).then(() => {
          copyBtn.title = t('sim.chat.copied');
          setTimeout(() => { copyBtn.title = t('sim.chat.copy'); }, 1500);
        });
      }
      return;
    }

    if (e.target.closest('#sim-model-btn')) {
      e.preventDefault();
      const menu = document.getElementById('sim-model-menu');
      if (menu?.hasAttribute('hidden')) openModelMenu();
      else closeModelMenu();
      return;
    }

    const modelItem = e.target.closest('.sim-model-item');
    if (modelItem?.dataset.modelId) {
      e.preventDefault();
      selectModel(modelItem.dataset.modelId);
      return;
    }

    if (e.target.closest('#sim-plus-btn')) {
      e.preventDefault();
      const menu = document.getElementById('sim-plus-menu');
      if (menu?.classList.contains('hidden')) openPlusMenu();
      else closePlusMenu();
      return;
    }

    const item = e.target.closest('.sim-plus-item');
    if (item) {
      e.preventDefault();
      if (item.dataset.action === 'upload') {
        closePlusMenu();
        document.getElementById('sim-file-input')?.click();
        return;
      }
      if (item.dataset.mode) setActiveMode(item.dataset.mode);
    }
  });

  document.getElementById('sim-model-menu')?.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModelMenu();
  });

  const goal = document.getElementById('goal');
  goal?.addEventListener('input', () => updateComposerState());
  updateComposerState();

  form.addEventListener('keydown', (e) => {
    if (e.target.closest('#run-panel')) return;
    if (e.key !== 'Enter') return;
    // IME composing (e.g. Chinese pinyin) — don't submit mid-composition
    if (e.isComposing || e.keyCode === 229) return;
    if (e.shiftKey) return; // Shift+Enter = newline
    const tag = (e.target?.tagName || '').toLowerCase();
    if (tag !== 'textarea') return;
    e.preventDefault();
    const btn = document.getElementById('start-btn');
    if (!btn?.disabled) form.requestSubmit();
  });

  form.addEventListener('submit', onSubmit);
}

export function renderChat(chatSessionIdParam = null) {
  const isNew = !chatSessionIdParam;
  return pageShell(`
    <form id="chat-form" class="sim-page sim-page--chat ${isNew ? 'is-empty' : 'is-active'}" data-chat-id="${escapeHtml(chatSessionIdParam || '')}">
      <div class="sim-main sim-main--chat custom-scrollbar">
        <div id="chat-center-stage" class="chat-center-stage">
          ${chatEmptyHeroHtml()}
          ${chatComposerPanel()}
          <div class="sim-chat-thread-wrap">
            <div id="sim-chat-thread" class="sim-chat-thread"></div>
          </div>
        </div>
      </div>
      <p class="sim-chat-disclaimer">${t('sim.chat.disclaimer')}</p>
    </form>
  `, { sidebarActive: 'chat', chatSessionId: chatSessionIdParam, mainClass: 'app-main--chat' });
}


/** Soft-switch chat session without remounting sidebar / composer (avoids jump). */
export async function switchChatSession(chatSessionIdParam = null) {
  const form = document.getElementById('chat-form');
  if (!form) return false;

  const loadGen = ++chatLoadGen;
  chatSessionId = chatSessionIdParam;
  form.dataset.chatId = chatSessionIdParam || '';

  const thread = document.getElementById('sim-chat-thread');
  closePlusMenu();
  closeModelMenu();

  if (!chatSessionIdParam) {
    chatMessages = [];
    renderChatThread();
    return true;
  }

  // Keep active layout while loading so the composer does not jump to center.
  form.classList.add('is-active');
  form.classList.remove('is-empty');
  if (thread) {
    thread.innerHTML = `<p class="sim-chat-loading">${escapeHtml(t('common.loading'))}</p>`;
  }

  try {
    await loadChatSession(chatSessionIdParam, { loadGen });
  } catch (e) {
    if (loadGen !== chatLoadGen) return true;
    chatMessages = [];
    if (thread) {
      thread.innerHTML = `<p class="sim-chat-error">${escapeHtml(e.message || String(e))}</p>`;
    }
  }
  return true;
}

export async function mountChat(chatSessionIdParam = null) {
  unmountChat();
  const loadGen = ++chatLoadGen;
  chatSessionId = chatSessionIdParam;
  chatMessages = [];
  const form = document.getElementById('chat-form');
  if (!form) return;

  setActiveMode('answer');
  void ensureChatRenderers().catch(() => {});
  await refreshModelSelect();

  if (chatSessionIdParam) {
    // Avoid empty-hero jump while fetching an existing session.
    form.classList.add('is-active');
    form.classList.remove('is-empty');
    try {
      await loadChatSession(chatSessionIdParam, { loadGen });
    } catch (e) {
      if (loadGen !== chatLoadGen) return;
      const thread = document.getElementById('sim-chat-thread');
      if (thread) thread.innerHTML = `<p class="sim-chat-error">${escapeHtml(e.message || String(e))}</p>`;
    }
  } else {
    renderChatThread();
  }

  const onModelsChanged = () => { void refreshModelSelect(); };
  window.addEventListener('prds:llm-models-changed', onModelsChanged);
  form._prdsModelsHandler = onModelsChanged;

  bindComposerHandlers(form, {
    onSubmit: async (e) => {
      e.preventDefault();
      const btn = document.getElementById('start-btn');
      if (btn?.disabled) return;
      const goalVal = (document.getElementById('goal')?.value || '').trim();
      if (!goalVal) {
        alert(t('sim.fillRequired'));
        return;
      }
      btn.dataset.loading = '1';
      btn.disabled = true;
      btn.innerHTML = startBtnHtml(true);
      try {
        await runQuickAnswer(goalVal);
      } finally {
        delete btn.dataset.loading;
        resetStartBtn(btn);
        updateStartButton();
      }
    },
  });
}

export function unmountChat() {
  chatLoadGen += 1;
  const form = document.getElementById('chat-form');
  if (form?._prdsModelsHandler) {
    window.removeEventListener('prds:llm-models-changed', form._prdsModelsHandler);
    delete form._prdsModelsHandler;
  }
  chatSessionId = null;
  chatMessages = [];
  closePlusMenu();
  closeModelMenu();
}

function updateComposerState() {
  if (document.getElementById('chat-form')) {
    updateStartButton();
    return;
  }
  updateReadyBar();
  updateStartButton();
}

function updateStartButton() {
  const btn = document.getElementById('start-btn');
  const goal = document.getElementById('goal');
  if (!btn || !goal) return;
  const ready = goal.value.trim().length > 0;
  btn.disabled = !ready || btn.dataset.loading === '1';
}

function updateReadyBar() {
  const goal = document.getElementById('goal');
  const bar = document.getElementById('ready-bar');
  const label = document.getElementById('ready-label');
  if (!goal || !bar) return;
  const goalLen = goal.value.trim().length;
  const pct = Math.min(100, Math.round((Math.min(goalLen, 80) / 80) * 100));
  bar.style.width = `${pct}%`;
  if (label) {
    label.textContent = pct >= 80 ? t('sim.ready.go') : pct >= 30 ? t('sim.ready.more') : t('sim.ready.empty');
  }
}

function startBtnHtml(spinning = false) {
  if (spinning) {
    return spinner('icon icon--md icon-spin');
  }
  return icon('send', 'icon icon--md');
}

function resetStartBtn(btn) {
  btn.innerHTML = startBtnHtml(false);
  btn.setAttribute('aria-label', startBtnLabel());
  btn.title = startBtnLabel();
}

function prefsForSim() {
  const prefs = getPrefs();
  return {
    agentCount: prefs.defaultAgentCount ?? 4,
    maxEvents: prefs.defaultMaxEvents ?? 6,
  };
}

function setActiveMode(mode) {
  if (mode === 'answer' && !location.hash.startsWith('#chat')) {
    location.hash = '#chat';
    return;
  }
  if (mode !== 'answer' && location.hash.startsWith('#chat')) {
    location.hash = mode === 'research' ? '#simulate' : '#simulate';
    sessionStorage.setItem('prds_sim_mode', mode);
    return;
  }
  activeMode = mode;
  const chip = document.getElementById('sim-mode-chip');
  if (chip) chip.textContent = t(modeLabelKey(mode));
  const goal = document.getElementById('goal');
  if (goal) goal.placeholder = modePlaceholder(mode);
  const btn = document.getElementById('start-btn');
  if (btn && btn.dataset.loading !== '1') resetStartBtn(btn);
  closePlusMenu();
}

export function applySimulateMode(mode) {
  if (!mode || !['simulate', 'research', 'answer'].includes(mode)) return;
  setActiveMode(mode);
}

function closePlusMenu() {
  const menu = document.getElementById('sim-plus-menu');
  const btn = document.getElementById('sim-plus-btn');
  menu?.classList.add('hidden');
  btn?.setAttribute('aria-expanded', 'false');
  if (menuOutsideHandler) {
    document.removeEventListener('click', menuOutsideHandler);
    menuOutsideHandler = null;
  }
}

function openPlusMenu() {
  closeModelMenu();
  const menu = document.getElementById('sim-plus-menu');
  const btn = document.getElementById('sim-plus-btn');
  if (!menu || !btn) return;
  menu.classList.remove('hidden');
  btn.setAttribute('aria-expanded', 'true');
  menuOutsideHandler = (e) => {
    if (e.target.closest('.sim-plus-wrap')) return;
    closePlusMenu();
  };
  setTimeout(() => document.addEventListener('click', menuOutsideHandler), 0);
}

function renderRunningPanel(simId, status) {
  const root = document.getElementById('sim-workspace');
  if (!root) return;
  const terminal = TERMINAL_STATUSES.has(status?.status);
  const paused = status?.status === 'paused';
  root.classList.add('sim-workspace-run');
  if (root.dataset.runId !== simId || !root.querySelector('#run-panel')) {
    root.dataset.runId = simId;
    root.innerHTML = `<div class="sim-main-inner"><section id="run-panel" class="glass-panel rounded-lg p-8 max-w-xl mx-auto" aria-live="polite">
      <h2 id="run-title" class="text-lg font-semibold mb-2"></h2>
      <p id="run-description" class="text-sm text-on-surface-variant mb-6"></p>
      <div class="flex justify-between text-xs mb-2"><span id="run-status"></span><span id="run-percent"></span></div>
      <progress id="run-progress" max="100" class="run-progress" aria-label="${t('history.phase')}"></progress>
      <p id="run-phase" class="text-sm mt-4"></p><p id="run-model" class="text-xs mt-3"></p>
      <div id="run-warnings" class="text-sm mt-3"></div><p id="run-error" class="text-error text-sm mt-3" role="alert"></p><p id="run-action-error" class="text-error text-sm mt-3" role="alert"></p>
      <div id="run-connection" class="text-sm mt-3" role="status"></div>
      <button type="button" id="run-reconnect" class="text-primary mt-2" hidden>${t('run.reconnect')}</button>
      <div class="flex flex-wrap gap-4 mt-6">
        <button type="button" id="run-pause" class="text-primary" hidden>${t('monitor.pause')}</button>
        <button type="button" id="run-resume" class="text-primary" hidden>${t('monitor.resume')}</button>
        <button type="button" id="run-cancel" class="text-error" hidden>${t('run.cancel')}</button>
        <button type="button" id="run-delete" class="text-error">${t('run.delete')}</button>
      </div>
      <div id="run-retry-controls" class="mt-4" hidden>
        <label for="run-retry-model" class="text-sm">${t('sim.modelSelect')}</label>
        <select id="run-retry-model" class="w-full rounded-lg mt-2" aria-label="${t('sim.modelSelect')}"></select>
        <button type="button" id="run-retry" class="text-primary mt-3">${t('run.retry')}</button>
      </div>
      <div id="run-injection" class="mt-6" hidden>
        <h3 class="text-sm font-semibold">${t('run.inject')}</h3>
        <p class="text-xs mt-2">${t('run.injectHint')}</p>
        <ul id="run-event-list" class="text-sm my-3"></ul>
        <div id="run-event-form" class="space-y-3">
          <label class="block text-sm">${t('run.eventDescription')}<textarea id="run-event-description" class="w-full rounded-lg mt-1" maxlength="500" required></textarea></label>
          <label class="block text-sm">${t('run.category')}<select id="run-event-category" class="w-full rounded-lg mt-1">
            ${['macro', 'market', 'org', 'resource'].map(c => `<option value="${c}">${t(`event.${c}`)}</option>`).join('')}
          </select></label>
          <div class="grid grid-cols-2 gap-3">
            <label class="text-sm">${t('run.impact')}<input id="run-event-impact" class="w-full rounded-lg mt-1" type="number" min="-1" max="1" step="0.1" value="0" required></label>
            <label class="text-sm">${t('run.severity')}<input id="run-event-severity" class="w-full rounded-lg mt-1" type="number" min="0.1" max="1" step="0.1" value="0.6" required></label>
          </div>
          <div class="flex gap-4">
            <button type="button" id="run-add-event" class="text-primary">${t('run.addEvent')}</button>
            <button type="button" id="run-clear-events" class="text-error">${t('monitor.clear')}</button>
          </div>
        </div>
      </div>
      <p class="text-xs text-outline mt-6">${escapeHtml(simId)}</p>
    </section></div>`;
  }
  const el = id => root.querySelector(`#${id}`);
  const pct = Math.round(status?.progress_pct || 0);
  el('run-title').textContent = terminal || paused ? statusLabel(status.status) : t('history.runningTitle');
  el('run-description').textContent = status?.status === 'interrupted' ? t('run.interruptedHint')
    : status?.status === 'cancelled' ? t('run.cancelledHint')
    : paused ? t('monitor.pausedShort') : t('history.runningDesc');
  el('run-status').textContent = statusLabel(status?.status || 'pending');
  el('run-percent').textContent = `${pct}%`;
  el('run-progress').value = pct;
  el('run-phase').textContent = `${phaseLabel(status?.phase || 'pending')} · ${status?.current_event_index || 0}/${status?.total_events || 0}`;
  el('run-model').textContent = `${t('run.model')}: ${status?.model_info?.model || t('run.modelUnknown')}`;
  el('run-error').textContent = status?.failure ? issueLabel(status.failure) : status?.error || '';
  el('run-warnings').textContent = (status?.warnings || []).map(issueLabel).join(' · ');
  el('run-pause').hidden = !status?.can_pause || status.pause_pending;
  el('run-resume').hidden = !paused;
  el('run-cancel').hidden = terminal;
  el('run-injection').hidden = !paused;
  el('run-retry-controls').hidden = !terminal;
  const select = el('run-retry-model');
  if (terminal && !select.dataset.ready) {
    const selected = status?.model_info?.model_id || '';
    select.innerHTML = `<option value="">${t('run.originalModel')}</option>` + modelCatalog.map(m =>
      `<option value="${escapeHtml(m.id)}" ${m.id === selected ? 'selected' : ''}>${escapeHtml(m.name || m.model)}</option>`).join('');
    select.dataset.ready = '1';
  }
  root.querySelectorAll('button, input, textarea, select').forEach(node => { node.disabled = runActionBusy; });
}

async function loadRunIntoWorkspace(simId) {
  const root = document.getElementById('sim-workspace');
  if (!root) return;
  const generation = runLoadGen;
  const controller = new AbortController();
  runAbort = controller;
  const current = () => generation === runLoadGen && root.isConnected;
  renderRunningPanel(simId, { status: 'pending' });
  const error = message => { const target = root.querySelector('#run-action-error'); if (current() && target) target.textContent = message; };
  const refreshEvents = async () => {
    const data = await API.getUserEvents(simId, { signal: controller.signal });
    if (!current()) return;
    const list = root.querySelector('#run-event-list');
    if (list) list.innerHTML = data.events.map(e => `<li class="py-1">${escapeHtml(e.description)}</li>`).join('') || `<li>${t('run.noEvents')}</li>`;
  };
  root.onclick = async e => {
    const button = e.target.closest('button');
    if (!button || !current()) return;
    if (button.id === 'run-reconnect') { statusStop?.reconnect(); return; }
    const actions = {
      'run-add-event': addInjected,
      'run-pause': () => API.pauseSimulation(simId),
      'run-resume': () => API.resumeSimulation(simId),
      'run-cancel': () => API.cancelSimulation(simId),
      'run-clear-events': async () => { await API.clearUserEvents(simId); await refreshEvents(); },
      'run-delete': async () => {
        if (!confirm(t('sidebar.deleteConfirm'))) return;
        await API.deleteSimulation(simId);
        if (current()) { location.hash = '#simulate'; void refreshSidebarNav({ simId: null }); }
      },
      'run-retry': async () => {
        const { simulation_id } = await API.retrySimulation(simId, root.querySelector('#run-retry-model').value || null);
        if (current()) location.hash = `#simulate/${simulation_id}`;
      },
    };
    const action = actions[button.id];
    if (!action || runActionBusy) return;
    runActionBusy = true;
    error('');
    button.disabled = true;
    try { await action(); }
    catch (err) { error(err.message); }
    finally {
      runActionBusy = false;
      if (current()) root.querySelectorAll('button, input, textarea, select').forEach(node => { node.disabled = false; });
    }
  };
  const addInjected = async () => {
    const fields = [...root.querySelectorAll('#run-event-form input, #run-event-form textarea')];
    if (fields.some(field => !field.reportValidity())) return;
    const text = root.querySelector('#run-event-description');
    try {
      await API.addUserEvent(simId, {
        description: text.value.trim(), category: root.querySelector('#run-event-category').value,
        impact: Number(root.querySelector('#run-event-impact').value), severity: Number(root.querySelector('#run-event-severity').value),
      });
      if (current()) { text.value = ''; await refreshEvents(); }
    } catch (err) { error(err.message); }
  };
  statusStop = API.pollStatus(simId, async data => {
    if (!current()) return;
    if (data.status === 'completed') {
      closePlusMenu();
      closeModelMenu();
      const form = root.closest('#sim-form');
      form?.classList.add('sim-page--completed');
      form?.querySelector('.sim-composer')?.remove();
      root.innerHTML = '<div class="sim-main-inner" id="results-root"></div>';
      await mountResults(simId, root.querySelector('#results-root'), { signal: controller.signal });
      if (current()) void refreshSidebarNav({ simId, chatId: null });
    } else {
      renderRunningPanel(simId, data);
      if (data.status === 'paused') {
        try { await refreshEvents(); } catch (err) { if (!controller.signal.aborted) error(err.message); }
      }
    }
  }, { onConnection: ({ state, lastUpdated }) => {
    if (!current()) return;
    const panel = root.querySelector('#run-connection');
    if (!panel) return;
    panel.textContent = state === 'connected' ? '' : t(`run.connection.${state}`);
    if (lastUpdated) panel.textContent += `${panel.textContent ? ' · ' : ''}${t('run.lastUpdated')}: ${lastUpdated.toLocaleTimeString()}`;
    root.querySelector('#run-reconnect').hidden = !['retrying', 'disconnected'].includes(state);
    if (state === 'missing') {
      root.querySelector('#run-title').textContent = t('run.missing');
      root.querySelectorAll('button, form, #run-retry-controls').forEach(n => { n.hidden = true; });
    }
  } });
}

async function handleUploadFiles(input) {
  const files = [...(input?.files || [])];
  if (!files.length) return;
  const msg = document.getElementById('sim-upload-msg');
  const targets = [...selectedKbIds];
  if (!targets.length) {
    alert(t('sim.uploadNeedKb'));
    input.value = '';
    return;
  }
  if (msg) msg.textContent = t('sim.uploading');
  const list = document.getElementById('sim-upload-list');
  try {
    const uploaded = [];
    for (const f of files) {
      for (const cat of targets) {
        await API.uploadKbDocument(f, cat);
      }
      uploaded.push(f.name);
    }
    if (list) {
      list.classList.remove('hidden');
      list.innerHTML = uploaded.map((name) =>
        `<span class="sim-upload-chip">${escapeHtml(name)}</span>`
      ).join('');
    }
    if (msg) msg.textContent = t('sim.uploadOk');
    await loadKbCategories();
  } catch (err) {
    if (msg) msg.textContent = err.message || String(err);
  } finally {
    input.value = '';
  }
}

export function unmountSimulate() {
  runLoadGen += 1;
  runAbort?.abort();
  runAbort = null;
  runActionBusy = false;
  const workspace = document.getElementById('sim-workspace');
  if (workspace) { workspace.onclick = null; workspace.onsubmit = null; }
  if (statusStop) {
    statusStop();
    statusStop = null;
  }
  const form = document.getElementById('sim-form');
  if (form?._prdsModeHandler) {
    window.removeEventListener('prds:set-sim-mode', form._prdsModeHandler);
    delete form._prdsModeHandler;
  }
  if (form?._prdsModelsHandler) {
    window.removeEventListener('prds:llm-models-changed', form._prdsModelsHandler);
    delete form._prdsModelsHandler;
  }
  closePlusMenu();
  closeModelMenu();
}

export async function mountSimulate(simId = null) {
  unmountSimulate();
  const form = document.getElementById('sim-form');
  if (!form) return;
  const generation = runLoadGen;
  selectedKbIds = new Set();

  await loadKbCategories();
  if (generation !== runLoadGen) return;
  await refreshModelSelect();
  if (generation !== runLoadGen) return;

  const preferred = sessionStorage.getItem('prds_sim_mode');
  if (preferred) sessionStorage.removeItem('prds_sim_mode');
  if (!simId && preferred === 'answer') {
    location.hash = '#chat';
    return;
  }
  setActiveMode(
    !simId && preferred && ['simulate', 'research'].includes(preferred)
      ? preferred
      : 'simulate',
  );

  if (simId) {
    await loadRunIntoWorkspace(simId);
  }

  const onExternalMode = (e) => {
    const mode = e.detail?.mode;
    if (mode) applySimulateMode(mode);
  };
  window.addEventListener('prds:set-sim-mode', onExternalMode);
  form._prdsModeHandler = onExternalMode;

  const onModelsChanged = () => { void refreshModelSelect(); };
  window.addEventListener('prds:llm-models-changed', onModelsChanged);
  form._prdsModelsHandler = onModelsChanged;

  form.addEventListener('click', (e) => {
    const dismiss = e.target.closest('[data-dismiss]');
    if (dismiss) {
      e.preventDefault();
      const panel = form.querySelector(`[data-sim-panel="${dismiss.dataset.dismiss}"]`);
      panel?.remove();
      return;
    }

    if (e.target.closest('#kb-drill-back')) {
      e.preventDefault();
      void loadKbCategories();
      return;
    }

    const catOpen = e.target.closest('.sim-kb-cat-open');
    if (catOpen) {
      e.preventDefault();
      void loadKbDocuments(catOpen.dataset.catId, catOpen.dataset.catName);
      return;
    }

    if (e.target.closest('#sim-model-btn')) {
      e.preventDefault();
      const menu = document.getElementById('sim-model-menu');
      if (menu?.hasAttribute('hidden')) openModelMenu();
      else closeModelMenu();
      return;
    }

    const modelItem = e.target.closest('.sim-model-item');
    if (modelItem?.dataset.modelId) {
      e.preventDefault();
      selectModel(modelItem.dataset.modelId);
      return;
    }

    if (e.target.closest('#sim-plus-btn')) {
      e.preventDefault();
      const menu = document.getElementById('sim-plus-menu');
      if (menu?.classList.contains('hidden')) openPlusMenu();
      else closePlusMenu();
      return;
    }

    const item = e.target.closest('.sim-plus-item');
    if (item) {
      e.preventDefault();
      if (item.dataset.action === 'upload') {
        closePlusMenu();
        document.getElementById('sim-file-input')?.click();
        return;
      }
      if (item.dataset.mode) setActiveMode(item.dataset.mode);
    }
  });

  document.getElementById('kb-select-list')?.addEventListener('change', (e) => {
    const input = e.target.closest('.kb-cat-check');
    if (!input) return;
    if (input.checked) selectedKbIds.add(input.value);
    else selectedKbIds.delete(input.value);
    updateComposerState();
  });

  document.getElementById('sim-model-menu')?.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModelMenu();
  });

  const goal = document.getElementById('goal');
  goal?.addEventListener('input', () => updateComposerState());
  updateComposerState();

  document.getElementById('sim-file-input')?.addEventListener('change', (e) => {
    handleUploadFiles(e.target);
  });

  form.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    // IME composing (e.g. Chinese pinyin) — don't submit mid-composition
    if (e.isComposing || e.keyCode === 229) return;
    if (e.shiftKey) return; // Shift+Enter = newline
    const tag = (e.target?.tagName || '').toLowerCase();
    if (tag !== 'textarea') return;
    e.preventDefault();
    const btn = document.getElementById('start-btn');
    if (!btn?.disabled) form.requestSubmit();
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (document.activeElement?.closest('#run-panel')) return;
    const btn = document.getElementById('start-btn');
    if (!btn || btn.disabled) return;
    const goalVal = (document.getElementById('goal')?.value || '').trim();
    if (!goalVal) {
      alert(t('sim.fillRequired'));
      return;
    }

    if (activeMode === 'research') {
      alert(t('sim.modeComingSoon'));
      return;
    }

    btn.dataset.loading = '1';
    btn.disabled = true;
    btn.innerHTML = startBtnHtml(true);
    btn.setAttribute('aria-label', t('sim.starting'));
    btn.title = t('sim.starting');

    // The goal alone is enough: the backend structures it against the selected
    // knowledge bases inside the run, so there is nothing to confirm up front.
    const payload = buildPayload({
      goal: goalVal,
      modelId: getSelectedModelId(),
      background: '',
      constraints: '',
      kbCategoryIds: [...selectedKbIds],
      ...prefsForSim(),
    });
    try {
      const { simulation_id } = await API.createSimulation(payload);
      localStorage.setItem('prds_last_sim', simulation_id);
      // Same-page: navigate to workspace run route (hashchange remounts with progress)
      location.hash = `#simulate/${simulation_id}`;
    } catch (err) {
      alert(t('sim.startFailed', { msg: err.message }));
      delete btn.dataset.loading;
      resetStartBtn(btn);
      updateStartButton();
    }
  });
}
