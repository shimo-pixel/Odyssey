import { API, phaseLabel } from '../api.js';
import { pageShell } from '../layout.js';
import { icon } from '../icons.js';
import { t } from '../i18n.js';

function getPipeline() {
  return [
    { phase: 'intake', iconName: 'schema', titleKey: 'phaseStep.intake' },
    { phase: 'event_plan', iconName: 'layers', titleKey: 'phaseStep.events' },
    { phase: 'branch_fork', iconName: 'users', titleKey: 'phaseStep.fork' },
    { phase: 'branch_sim', iconName: 'refresh', titleKey: 'phaseStep.branchSim' },
    { phase: 'scoring', iconName: 'metrics', titleKey: 'phaseStep.scoring' },
    { phase: 'synthesis', iconName: 'merge', titleKey: 'phaseStep.converge' },
  ];
}

export function renderModel() {
  return pageShell(`
    <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20">
      <header class="mb-10">
        <h1 class="text-2xl font-semibold text-on-surface tracking-tight">${t('model.title')}</h1>
        <p class="text-sm text-on-surface-variant mt-2 max-w-2xl leading-relaxed">${t('model.desc')}</p>
      </header>

      <section class="mb-12">
        <h2 class="text-sm font-medium mb-4">${t('model.pipeline')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3" id="pipeline-grid">
          ${getPipeline().map((p, i) => pipelineCard(p, i + 1)).join('')}
        </div>
      </section>

      <section class="mb-12 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="glass-panel p-6 rounded-lg">
          <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
            ${icon('brain', 'icon icon--md text-primary')}${t('model.llmLayer')}
          </h2>
          <div id="llm-config" class="space-y-4">
            <div class="animate-pulse h-20 bg-surface-container rounded-lg"></div>
          </div>
        </div>
        <div class="glass-panel p-6 rounded-lg">
          <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
            ${icon('tune', 'icon icon--md text-primary')}${t('model.engineParams')}
          </h2>
          <div id="engine-config" class="space-y-3">
            <div class="animate-pulse h-20 bg-surface-container rounded-lg"></div>
          </div>
        </div>
      </section>

      <section>
        <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
          ${icon('functions', 'icon icon--md text-primary')}${t('model.branchMechanism')}
        </h2>
        <div class="glass-panel p-6 rounded-lg">
          <p class="text-sm text-on-surface-variant leading-relaxed">${t('model.branchMechanismDesc')}</p>
        </div>
      </section>
    </div>
  `, { sidebarActive: 'model' });
}

function pipelineCard(p, n) {
  const tones = ['blue', 'green', 'violet', 'teal', 'amber', 'coral'];
  const tone = tones[(n - 1) % tones.length];
  const num = String(n).padStart(2, '0');
  return `
    <div class="sim-pipeline-step" data-tone="${tone}">
      <span class="sim-pipeline-icon">${icon(p.iconName, 'icon icon--sm')}</span>
      <div class="sim-pipeline-body">
        <div class="flex items-center gap-2 mb-0.5">
          <span class="sim-pipeline-num">${num}</span>
          <h3 class="sim-pipeline-title">${t(p.titleKey)}</h3>
        </div>
        <p class="sim-pipeline-desc">${t(`${p.titleKey}.desc`)}</p>
        <span class="inline-block mt-1 text-[10px] font-mono text-outline">${phaseLabel(p.phase)}</span>
      </div>
    </div>`;
}

function configRow(label, value) {
  return `<div class="flex justify-between items-center py-2 border-b border-outline-variant/40 last:border-0">
    <span class="text-sm text-on-surface-variant">${label}</span>
    <span class="font-mono text-sm font-medium text-on-surface">${value}</span>
  </div>`;
}

export async function mountModel() {
  try {
    const cfg = await API.getConfig();
    let llm = {};
    try { llm = await API.getLlmSettings(); } catch (_) {}
    document.getElementById('llm-config').innerHTML = `
      ${configRow(t('model.decisionModel'), llm.model || cfg.llm_model)}
      ${configRow(t('model.analysisModel'), llm.model_analysis || cfg.llm_model_analysis)}
      ${configRow(t('model.maxConcurrent'), cfg.max_concurrent_llm)}
      <div class="mt-3 text-xs text-on-surface-variant">${(llm.configured ?? cfg.llm_configured) ? t('model.apiOk') : t('model.apiMissing')}</div>`;
    document.getElementById('engine-config').innerHTML = `
      ${configRow(t('model.defaultPaths'), cfg.default_agent_count)}
      ${configRow(t('model.defaultMaxEvents'), cfg.default_max_events)}
      ${configRow(t('model.maxSteps'), cfg.max_steps ?? '—')}`;
  } catch {
    document.getElementById('llm-config').innerHTML = `<p class="text-sm text-error">${t('model.configFailed')}</p>`;
  }
}
