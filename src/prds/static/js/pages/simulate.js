import { API, buildPayload, DOMAIN_PROFILES, getPhaseSteps } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import { applyPrefsToSimulateForm } from './settings.js';
import { buildTimelinePreview, timeConfigFrom, unitLengthLabel } from '../time.js';

const PIPELINE_ICONS = ['psychology', 'flag', 'schema', 'hub', 'groups', 'merge'];
const PIPELINE_THEMES = ['yellow', 'blue', 'purple', 'green', 'pink', 'orange'];
const PIPELINE_DESC_KEYS = ['analysis', 'goal', 'ontology', 'knowledge', 'spawn', 'converge'];

const COMPOSER_FIELDS = [
  { id: 'background', icon: 'edit_note', labelKey: 'sim.background', descKey: 'sim.background.hint', chipClass: 'sim-field-chip--blue' },
  { id: 'goal', icon: 'flag', labelKey: 'sim.goal', descKey: 'sim.goal.placeholder', chipClass: 'sim-field-chip--green' },
  { id: 'constraints', icon: 'tune', labelKey: 'sim.constraints', descKey: 'sim.constraints.placeholder', chipClass: 'sim-field-chip--orange' },
];

function unitOptions(selected) {
  return ['day', 'week', 'month', 'quarter', 'year'].map(u =>
    `<option value="${u}" ${selected === u ? 'selected' : ''}>${t(`unit.${u}`)}</option>`,
  ).join('');
}

function settingsPanel() {
  return `
    <aside class="sim-settings-panel custom-scrollbar">
      <div class="sim-settings-header">
        <h2 class="sim-settings-title">${t('sim.params')}</h2>
        <span class="sim-settings-badge">${t('sim.standby')}</span>
      </div>

      <div class="sim-settings-section">
        <div class="config-chip">
          <div class="flex justify-between items-center">
            <span class="text-sm font-medium text-on-surface">${t('sim.agentCount')}</span>
            <span id="agent-val" class="font-mono text-sm font-bold text-primary">10</span>
          </div>
          <input type="range" name="agentCount" min="5" max="100" value="10" id="agent-range"/>
          <span class="text-[10px] text-on-surface-variant">${t('sim.agentCount.hint')}</span>
        </div>
        <div class="config-chip">
          <div class="flex justify-between items-center">
            <span class="text-sm font-medium text-on-surface">${t('sim.periods')}</span>
            <span id="period-val" class="font-mono text-sm font-bold text-primary">6</span>
          </div>
          <input type="range" name="periods" min="3" max="24" value="6" id="period-range"/>
          <span class="text-[10px] text-on-surface-variant">${t('sim.periods.hint')}</span>
        </div>
        <div class="config-chip">
          <div class="flex justify-between items-center">
            <span class="text-sm font-medium text-on-surface">${t('sim.replications')}</span>
            <span id="rep-val" class="font-mono text-sm font-bold text-primary">1</span>
          </div>
          <input type="range" name="replications" min="1" max="5" value="1" id="rep-range"/>
          <span class="text-[10px] text-on-surface-variant">${t('sim.replications.hint')}</span>
        </div>
      </div>

      <div class="sim-settings-section">
        <div class="flex items-center gap-2 mb-3">
          <span class="material-symbols-outlined text-primary text-lg">schedule</span>
          <span class="text-sm font-medium text-on-surface">${t('sim.periodTime')}</span>
        </div>
        <div class="space-y-3">
          <div>
            <label class="sim-field-label">${t('sim.timeUnit')}</label>
            <select name="periodTimeUnit" id="period-time-unit" class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2">
              ${unitOptions('month')}
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="sim-field-label">${t('sim.periodLength')}</label>
              <input type="number" name="periodTimeLength" id="period-time-length" min="1" max="52" value="1"
                class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2"/>
            </div>
            <div>
              <label class="sim-field-label">${t('sim.startDate')}</label>
              <input type="date" name="simulationStartDate" id="simulation-start-date"
                class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2"/>
            </div>
          </div>
          <p id="period-time-desc" class="text-[11px] text-on-surface-variant leading-relaxed"></p>
        </div>
      </div>

      <div class="sim-settings-section">
        <p class="sim-field-label mb-2">${t('sim.timelinePreview')}</p>
        <div id="timeline-preview" class="space-y-1.5 max-h-40 overflow-y-auto custom-scrollbar"></div>
      </div>

      <div class="sim-settings-section mt-auto">
        <div class="mt-4">
          <div class="flex justify-between items-center mb-2">
            <span class="text-xs text-on-surface-variant font-medium">${t('sim.readiness')}</span>
            <span class="text-[10px] font-mono text-outline" id="ready-label">${t('sim.ready.empty')}</span>
          </div>
          <div class="h-1.5 bg-surface-variant rounded-full overflow-hidden">
            <div class="h-full rounded-full w-0 transition-all duration-500" style="background:var(--g-blue)" id="ready-bar"></div>
          </div>
        </div>
      </div>
    </aside>`;
}

function fieldPickerMenu() {
  return COMPOSER_FIELDS.map(field => `
    <button type="button" class="sim-picker-item" data-field="${field.id}" role="menuitem">
      <span class="sim-picker-icon sim-picker-icon--${field.id}">
        <span class="material-symbols-outlined">${field.icon}</span>
      </span>
      <span class="sim-picker-text">
        <span class="sim-picker-title">${t(field.labelKey)}</span>
        <span class="sim-picker-desc">${t(field.descKey)}</span>
      </span>
      <span class="material-symbols-outlined sim-picker-check" data-check="${field.id}">check</span>
    </button>`).join('');
}

function composerPanel(bgPh) {
  const defaultField = COMPOSER_FIELDS[0];
  return `
    <div class="sim-composer">
      <div class="sim-composer-inner">
        <div class="sim-composer-body">
          <textarea id="background" name="background" data-field="background" rows="3"
            class="sim-composer-textarea active"
            placeholder="${bgPh}"></textarea>
          <textarea id="goal" name="goal" data-field="goal" rows="3"
            class="sim-composer-textarea"
            placeholder="${t('sim.goal.placeholder')}" hidden></textarea>
          <textarea name="constraints" data-field="constraints" rows="3"
            class="sim-composer-textarea"
            placeholder="${t('sim.constraints.placeholder')}" hidden></textarea>
        </div>
        <div class="sim-composer-bar">
          <div class="sim-composer-bar-left">
            <div class="sim-picker-wrap">
              <button type="button" id="field-picker-btn" class="sim-icon-btn" aria-haspopup="menu" aria-expanded="false" title="${t('sim.fieldPicker')}">
                <span class="material-symbols-outlined">add</span>
              </button>
              <div id="field-picker-menu" class="sim-picker-menu" role="menu" hidden>
                ${fieldPickerMenu()}
              </div>
            </div>
            <button type="button" id="field-chip-btn" class="sim-field-chip ${defaultField.chipClass}" aria-haspopup="menu">
              <span class="material-symbols-outlined text-base" id="field-chip-icon">${defaultField.icon}</span>
              <span id="field-chip-label">${t(defaultField.labelKey)}</span>
            </button>
          </div>
          <div class="sim-composer-bar-right">
            <span id="composer-count" class="sim-composer-count">${t('char.count', { n: 0 })}</span>
            <button type="submit" id="start-btn" class="sim-run-btn" disabled>
              ${startBtnHtml(false)}
              <kbd class="sim-run-kbd hidden sm:inline">${t('sim.runShortcut')}</kbd>
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

export function renderSimulate() {
  const bgPh = t('sim.background.placeholder').replace(/\n/g, '&#10;');
  const phaseSteps = getPhaseSteps();

  return pageShell(`
    <form id="sim-form" class="sim-page">
      ${settingsPanel()}

      <div class="sim-main custom-scrollbar">
        <div class="sim-main-inner">
          <section class="simulate-hero p-6 lg:p-8">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full g-chip g-chip-blue text-xs font-medium mb-3">
              <span class="material-symbols-outlined text-sm">hub</span>
              ${t('sim.hero.badge')}
            </div>
            <h1 class="text-2xl lg:text-3xl font-normal text-on-surface tracking-tight leading-tight">${t('sim.hero.title')}</h1>
            <p class="text-sm text-on-surface-variant mt-2 leading-relaxed max-w-2xl">${t('sim.hero.desc')}</p>
          </section>

          <section class="mt-8">
            <h2 class="text-[11px] font-medium text-on-surface-variant uppercase tracking-widest mb-4">${t('sim.pipeline')}</h2>
            <div class="sim-pipeline-grid">
              ${phaseSteps.map((s, i) => pipelineCard(s.label, i)).join('')}
            </div>
          </section>

          <section class="mt-8 p-4 rounded-xl border border-outline-variant bg-surface-container-low">
            <p class="text-xs text-on-surface-variant font-medium mb-1">${t('sim.tip.title')}</p>
            <p class="text-[13px] text-on-surface-variant leading-relaxed">${t('sim.tip.body')}</p>
          </section>
        </div>
      </div>

      ${composerPanel(bgPh)}
    </form>
  `, { sidebarActive: 'simulate', mainClass: 'ml-0 lg:ml-60' });
}

function pipelineCard(label, index) {
  const icon = PIPELINE_ICONS[index] || 'circle';
  const theme = PIPELINE_THEMES[index] || 'blue';
  const descKey = PIPELINE_DESC_KEYS[index] || 'analysis';
  return `
    <div class="sim-model-card sim-model-card--${theme}">
      <div class="sim-model-icon-wrap">
        <span class="material-symbols-outlined">${icon}</span>
      </div>
      <h3 class="sim-model-title">${label}</h3>
      <p class="sim-model-desc">${t(`phaseStep.${descKey}.desc`)}</p>
    </div>`;
}

let activeComposerField = 'background';

function getComposerField(id) {
  return COMPOSER_FIELDS.find(f => f.id === id) || COMPOSER_FIELDS[0];
}

function switchComposerField(fieldId) {
  if (fieldId === activeComposerField) {
    closeFieldPicker();
    return;
  }
  const prev = document.querySelector(`.sim-composer-textarea[data-field="${activeComposerField}"]`);
  const next = document.querySelector(`.sim-composer-textarea[data-field="${fieldId}"]`);
  if (!prev || !next) return;

  prev.hidden = true;
  prev.classList.remove('active');
  next.hidden = false;
  next.classList.add('active');
  activeComposerField = fieldId;

  const field = getComposerField(fieldId);
  const chip = document.getElementById('field-chip-btn');
  const chipIcon = document.getElementById('field-chip-icon');
  const chipLabel = document.getElementById('field-chip-label');
  if (chip) {
    chip.className = `sim-field-chip ${field.chipClass}`;
  }
  if (chipIcon) chipIcon.textContent = field.icon;
  if (chipLabel) chipLabel.textContent = t(field.labelKey);

  document.querySelectorAll('.sim-picker-check').forEach(el => {
    el.style.visibility = el.dataset.check === fieldId ? 'visible' : 'hidden';
  });
  document.querySelectorAll('.sim-picker-item').forEach(el => {
    el.classList.toggle('active', el.dataset.field === fieldId);
  });

  closeFieldPicker();
  next.focus();
  updateComposerState();
}

function openFieldPicker(anchor) {
  const menu = document.getElementById('field-picker-menu');
  const btn = document.getElementById('field-picker-btn');
  if (!menu) return;
  menu.hidden = false;
  btn?.setAttribute('aria-expanded', 'true');
  document.querySelectorAll('.sim-picker-check').forEach(el => {
    el.style.visibility = el.dataset.check === activeComposerField ? 'visible' : 'hidden';
  });
  document.querySelectorAll('.sim-picker-item').forEach(el => {
    el.classList.toggle('active', el.dataset.field === activeComposerField);
  });
}

function closeFieldPicker() {
  const menu = document.getElementById('field-picker-menu');
  const btn = document.getElementById('field-picker-btn');
  if (menu) menu.hidden = true;
  btn?.setAttribute('aria-expanded', 'false');
}

function toggleFieldPicker() {
  const menu = document.getElementById('field-picker-menu');
  if (!menu) return;
  if (menu.hidden) openFieldPicker();
  else closeFieldPicker();
}

function updateComposerState() {
  const bg = document.getElementById('background');
  const goal = document.getElementById('goal');
  const constraints = document.querySelector('[name="constraints"]');
  const activeField = document.querySelector(`.sim-composer-textarea[data-field="${activeComposerField}"]`);
  const countEl = document.getElementById('composer-count');

  if (countEl && activeField) {
    countEl.textContent = t('char.count', { n: activeField.value.trim().length });
  }

  updateReadyBar();
  updateStartButton();
}

function updateStartButton() {
  const btn = document.getElementById('start-btn');
  const bg = document.getElementById('background');
  const goal = document.getElementById('goal');
  if (!btn || !bg || !goal) return;
  const ready = bg.value.trim().length > 0 && goal.value.trim().length > 0;
  btn.disabled = !ready || btn.dataset.loading === '1';
}

function updateReadyBar() {
  const bg = document.getElementById('background');
  const goal = document.getElementById('goal');
  const bar = document.getElementById('ready-bar');
  const label = document.getElementById('ready-label');
  if (!bg || !goal || !bar) return;
  const bgLen = bg.value.trim().length;
  const goalLen = goal.value.trim().length;
  const pct = Math.min(100, Math.round((Math.min(bgLen, 200) / 200) * 50 + (Math.min(goalLen, 80) / 80) * 50));
  bar.style.width = `${pct}%`;
  if (label) {
    label.textContent = pct >= 80 ? t('sim.ready.go') : pct >= 40 ? t('sim.ready.more') : t('sim.ready.empty');
  }
}

function startBtnHtml(spinning = false) {
  if (spinning) {
    return `<span class="material-symbols-outlined animate-spin text-base">progress_activity</span><span>${t('sim.starting')}</span>`;
  }
  return `<span>${t('sim.start')}</span>`;
}

function resetStartBtn(btn) {
  btn.innerHTML = `${startBtnHtml(false)}<kbd class="sim-run-kbd hidden sm:inline">${t('sim.runShortcut')}</kbd>`;
}

function applyDomainDefaults(form) {
  const profile = DOMAIN_PROFILES.startup;
  const agentRange = document.getElementById('agent-range');
  const periodRange = document.getElementById('period-range');
  if (agentRange) {
    agentRange.value = String(profile.defaultAgents);
    document.getElementById('agent-val').textContent = agentRange.value;
  }
  if (periodRange) {
    periodRange.value = String(profile.defaultPeriods);
    document.getElementById('period-val').textContent = periodRange.value;
  }
  updateTimelinePreview(form);
}

export function mountSimulate() {
  const form = document.getElementById('sim-form');
  if (!form) return;
  applyPrefsToSimulateForm(form);
  applyDomainDefaults(form);
  updateTimelinePreview(form);

  document.getElementById('field-picker-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleFieldPicker();
  });
  document.getElementById('field-chip-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleFieldPicker();
  });
  document.getElementById('field-picker-menu')?.addEventListener('click', (e) => {
    const item = e.target.closest('.sim-picker-item');
    if (item?.dataset.field) switchComposerField(item.dataset.field);
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.sim-picker-wrap') && !e.target.closest('#field-chip-btn')) {
      closeFieldPicker();
    }
  });

  const bg = document.getElementById('background');
  const goal = document.getElementById('goal');
  const constraints = form.querySelector('[name="constraints"]');
  [bg, goal, constraints].forEach(el => {
    if (!el) return;
    el.addEventListener('input', () => updateComposerState());
  });
  updateComposerState();

  const agentRange = document.getElementById('agent-range');
  const periodRange = document.getElementById('period-range');
  agentRange?.addEventListener('input', () => {
    document.getElementById('agent-val').textContent = agentRange.value;
  });
  periodRange?.addEventListener('input', () => {
    document.getElementById('period-val').textContent = periodRange.value;
    updateTimelinePreview(form);
  });
  const repRange = document.getElementById('rep-range');
  repRange?.addEventListener('input', () => {
    document.getElementById('rep-val').textContent = repRange.value;
  });

  ['periodTimeUnit', 'periodTimeLength', 'simulationStartDate'].forEach(name => {
    form.querySelector(`[name="${name}"]`)?.addEventListener('input', () => updateTimelinePreview(form));
    form.querySelector(`[name="${name}"]`)?.addEventListener('change', () => updateTimelinePreview(form));
  });
  updateTimelinePreview(form);

  form.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      const btn = document.getElementById('start-btn');
      if (!btn?.disabled) form.requestSubmit();
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('start-btn');
    if (btn.disabled) return;
    const fd = new FormData(form);
    const bgVal = (fd.get('background') || '').toString().trim();
    const goalVal = (fd.get('goal') || '').toString().trim();
    if (!bgVal || !goalVal) {
      alert(t('sim.fillRequired'));
      return;
    }
    btn.dataset.loading = '1';
    btn.disabled = true;
    btn.innerHTML = `<span class="material-symbols-outlined animate-spin text-base">progress_activity</span><span>${t('refine.analyzing')}</span>`;

    const baseForm = Object.fromEntries(fd.entries());
    try {
      const proposal = await API.refineInput({
        background: bgVal,
        goal: goalVal,
        constraints: (baseForm.constraints || '').split('\n').map(s => s.trim()).filter(Boolean),
        domain_id: 'startup',
      });
      openRefineReview(proposal, baseForm);
    } catch (err) {
      alert(t('refine.failed', { msg: err.message }));
    } finally {
      delete btn.dataset.loading;
      resetStartBtn(btn);
      updateStartButton();
    }
  });
}

function listToText(arr) {
  return (arr || []).join('\n');
}

function chipList(items) {
  if (!items || !items.length) return `<span class="text-xs text-on-surface-variant">${t('common.none')}</span>`;
  return `<ul class="refine-bullets">${items.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
}

function openRefineReview(proposal, baseForm) {
  document.getElementById('refine-overlay')?.remove();
  const overlay = document.createElement('div');
  overlay.id = 'refine-overlay';
  overlay.className = 'refine-overlay';
  overlay.innerHTML = `
    <div class="refine-modal custom-scrollbar" role="dialog" aria-modal="true">
      <div class="refine-modal-head">
        <div>
          <span class="text-xs text-primary font-bold uppercase tracking-widest">${t('refine.tag')}</span>
          <h2 class="text-lg font-bold text-on-surface mt-1">${t('refine.title')}</h2>
          <p class="text-xs text-on-surface-variant mt-1 max-w-xl">${t('refine.subtitle')}</p>
        </div>
        <button type="button" id="refine-close" class="refine-icon-btn" aria-label="${t('common.close')}">
          <span class="material-symbols-outlined">close</span>
        </button>
      </div>

      ${proposal.notes ? `<div class="refine-note"><span class="material-symbols-outlined text-primary text-base">auto_awesome</span><p>${escapeHtml(proposal.notes)}</p></div>` : ''}

      <div class="refine-grid">
        <label class="refine-field">
          <span class="refine-label">${t('sim.background')}</span>
          <textarea id="refine-background" rows="5" class="refine-input">${escapeHtml(proposal.background || '')}</textarea>
        </label>
        <label class="refine-field">
          <span class="refine-label">${t('sim.goal')}</span>
          <textarea id="refine-goal" rows="3" class="refine-input">${escapeHtml(proposal.goal || '')}</textarea>
        </label>
        <div class="refine-cols">
          <label class="refine-field">
            <span class="refine-label">${t('sim.constraints')}</span>
            <textarea id="refine-constraints" rows="4" class="refine-input" placeholder="${t('refine.onePerLine')}">${escapeHtml(listToText(proposal.constraints))}</textarea>
          </label>
          <label class="refine-field">
            <span class="refine-label">${t('refine.risks')}</span>
            <textarea id="refine-risks" rows="4" class="refine-input" placeholder="${t('refine.onePerLine')}">${escapeHtml(listToText(proposal.risks))}</textarea>
          </label>
          <label class="refine-field">
            <span class="refine-label">${t('refine.opportunities')}</span>
            <textarea id="refine-opportunities" rows="4" class="refine-input" placeholder="${t('refine.onePerLine')}">${escapeHtml(listToText(proposal.opportunities))}</textarea>
          </label>
        </div>
      </div>

      ${(proposal.assumptions?.length || proposal.open_questions?.length) ? `
        <div class="refine-cols mt-2">
          ${proposal.assumptions?.length ? `<div class="refine-aside refine-aside--warn">
            <span class="refine-aside-title"><span class="material-symbols-outlined text-base">fact_check</span>${t('refine.assumptions')}</span>
            ${chipList(proposal.assumptions)}
          </div>` : ''}
          ${proposal.open_questions?.length ? `<div class="refine-aside">
            <span class="refine-aside-title"><span class="material-symbols-outlined text-base">help</span>${t('refine.openQuestions')}</span>
            ${chipList(proposal.open_questions)}
          </div>` : ''}
        </div>` : ''}

      ${Object.keys(proposal.success_metrics || {}).length ? `
        <div class="refine-aside mt-2">
          <span class="refine-aside-title"><span class="material-symbols-outlined text-base">track_changes</span>${t('refine.successMetrics')}</span>
          <p class="text-xs text-on-surface-variant mb-2">${t('refine.successMetricsHint')}</p>
          <div class="refine-metrics-chips">
            ${Object.entries(proposal.success_metrics).map(([k, v]) =>
              `<span class="refine-metric-chip"><strong>${escapeHtml(k)}</strong> ≥ ${escapeHtml(String(v))}</span>`
            ).join('')}
          </div>
        </div>` : ''}

      <div class="refine-actions">
        <button type="button" id="refine-cancel" class="refine-btn refine-btn--ghost">${t('refine.editAgain')}</button>
        <button type="button" id="refine-confirm" class="refine-btn refine-btn--primary">
          <span class="material-symbols-outlined text-base">rocket_launch</span>${t('refine.confirm')}
        </button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.getElementById('refine-close').addEventListener('click', close);
  document.getElementById('refine-cancel').addEventListener('click', close);

  document.getElementById('refine-confirm').addEventListener('click', async () => {
    const confirmBtn = document.getElementById('refine-confirm');
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = `<span class="material-symbols-outlined animate-spin text-base">progress_activity</span>${t('sim.starting')}`;
    const payload = buildPayload({
      ...baseForm,
      background: document.getElementById('refine-background').value.trim(),
      goal: document.getElementById('refine-goal').value.trim(),
      constraints: document.getElementById('refine-constraints').value,
      risks: document.getElementById('refine-risks').value,
      opportunities: document.getElementById('refine-opportunities').value,
      success_metrics: proposal.success_metrics || {},
    });
    try {
      const { simulation_id } = await API.createSimulation(payload);
      localStorage.setItem('prds_last_sim', simulation_id);
      close();
      location.hash = `#monitor/${simulation_id}`;
    } catch (err) {
      alert(t('sim.startFailed', { msg: err.message }));
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = `<span class="material-symbols-outlined text-base">rocket_launch</span>${t('refine.confirm')}`;
    }
  });
}

function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function updateTimelinePreview(form) {
  const fd = new FormData(form);
  const cfg = timeConfigFrom({
    period_time_unit: fd.get('periodTimeUnit'),
    period_time_length: fd.get('periodTimeLength'),
    simulation_start_date: fd.get('simulationStartDate') || null,
  });
  const periods = Number(fd.get('periods')) || 6;
  const desc = document.getElementById('period-time-desc');
  const preview = document.getElementById('timeline-preview');
  if (desc) {
    desc.textContent = unitLengthLabel(cfg.period_time_unit, cfg.period_time_length);
  }
  if (preview) {
    const items = buildTimelinePreview(cfg, periods);
    preview.innerHTML = items.map(item => {
      if (item.gap) {
        return `
      <div class="flex items-center justify-center gap-1 text-[11px] text-on-surface-variant py-0.5">
        <span class="material-symbols-outlined text-sm">more_vert</span>
        <span>${t('sim.timelineMore', { n: item.hidden })}</span>
      </div>`;
      }
      return `
      <div class="flex items-center gap-2 text-xs bg-surface-container-low rounded-lg px-3 py-1.5">
        <span class="font-mono font-bold text-primary shrink-0">T${item.period}</span>
        <span class="text-on-surface-variant truncate">${item.label.split(' · ')[0]}</span>
      </div>`;
    }).join('');
  }
}
