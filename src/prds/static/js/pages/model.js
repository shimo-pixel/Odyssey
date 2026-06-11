import { API, getActionLabels, phaseLabel } from '../api.js';
import { pageShell } from '../layout.js';
import { icon } from '../icons.js';
import { t } from '../i18n.js';

function getPipeline() {
  return [
    { phase: 'ontology', iconName: 'schema', titleKey: 'model.pipe.graphrag', descKey: 'model.pipe.graphragDesc' },
    { phase: 'world_init', iconName: 'layers', titleKey: 'model.pipe.world', descKey: 'model.pipe.worldDesc' },
    { phase: 'agent_spawn', iconName: 'users', titleKey: 'model.pipe.spawn', descKey: 'model.pipe.spawnDesc' },
    { phase: 'simulation', iconName: 'refresh', titleKey: 'model.pipe.loop', descKey: 'model.pipe.loopDesc' },
    { phase: 'scoring', iconName: 'metrics', titleKey: 'model.pipe.scoring', descKey: 'model.pipe.scoringDesc' },
    { phase: 'trajectory', iconName: 'route', titleKey: 'model.pipe.trajectory', descKey: 'model.pipe.trajectoryDesc' },
    { phase: 'counterfactual', iconName: 'route', titleKey: 'model.pipe.counterfactual', descKey: 'model.pipe.counterfactualDesc' },
    { phase: 'synthesis', iconName: 'merge', titleKey: 'model.pipe.synthesis', descKey: 'model.pipe.synthesisDesc' },
  ];
}

export function renderModel() {
  const actions = getActionLabels();
  return pageShell(`
    <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20">
      <header class="mb-10">
        <h1 class="text-2xl font-semibold text-on-surface tracking-tight">${t('model.title')}</h1>
        <p class="text-sm text-on-surface-variant mt-2 max-w-2xl leading-relaxed">${t('model.desc')}</p>
      </header>

      <section class="mb-12">
        <h2 class="text-sm font-medium mb-4">${t('model.pipeline')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3" id="pipeline-grid">
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

      <section class="mb-12">
        <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
          ${icon('touch', 'icon icon--md text-primary')}${t('model.actionSpace')}
        </h2>
        <p class="text-sm text-on-surface-variant mb-4">${t('model.actionSpaceDesc')}</p>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-2">
          ${Object.entries(actions).map(([key, label]) => actionTile(key, label)).join('')}
        </div>
      </section>

      <section>
        <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
          ${icon('functions', 'icon icon--md text-primary')}${t('model.scoring')}
        </h2>
        <div class="glass-panel p-6 rounded-lg font-mono text-sm">
          <p class="text-on-surface mb-4">Score = GoalAchievement × 40% + ResourceEfficiency × 20% + RiskControl × 15% + ExecutionQuality × 15% + Adaptability × 10%</p>
          <div class="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
            ${scoreWeight(t('model.score.goal'), '40%')}
            ${scoreWeight(t('model.score.efficiency'), '20%')}
            ${scoreWeight(t('model.score.risk'), '15%')}
            ${scoreWeight(t('model.score.execution'), '15%')}
            ${scoreWeight(t('model.score.adapt'), '10%')}
          </div>
        </div>
      </section>
    </div>
  `, { sidebarActive: 'model', mainClass: 'ml-[13.5rem] min-h-screen bg-background' });
}

function pipelineCard(p, n) {
  const tones = ['blue', 'green', 'violet', 'teal', 'amber', 'coral', 'blue', 'violet'];
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
        <p class="sim-pipeline-desc">${t(p.descKey)}</p>
        <span class="inline-block mt-1 text-[10px] font-mono text-outline">${phaseLabel(p.phase)}</span>
      </div>
    </div>`;
}

function actionTile(key, label) {
  return `
    <div class="bg-surface-container-low border border-outline-variant rounded-lg p-3 text-center hover:border-primary/30 transition-colors">
      <span class="text-sm font-medium text-on-surface block">${label}</span>
      <span class="text-[10px] font-mono text-outline">${key}</span>
    </div>`;
}

function scoreWeight(name, pct) {
  return `<div class="bg-surface-container-low rounded-lg p-3 text-center">
    <span class="text-primary font-semibold block">${pct}</span>
    <span class="text-on-surface-variant">${name}</span>
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
    const cfg = await fetch('/config').then(r => r.json());
    document.getElementById('llm-config').innerHTML = `
      ${configRow(t('model.decisionModel'), cfg.llm_model)}
      ${configRow(t('model.analysisModel'), cfg.llm_model_analysis)}
      ${configRow(t('model.maxConcurrent'), cfg.max_concurrent_llm)}
      <div class="mt-3 text-xs text-on-surface-variant">${cfg.llm_configured ? t('model.apiOk') : t('model.apiMissing')}</div>`;
    document.getElementById('engine-config').innerHTML = `
      ${configRow(t('model.defaultPaths'), cfg.default_agent_count)}
      ${configRow(t('model.defaultMaxEvents'), cfg.default_max_events ?? cfg.default_periods)}
      ${configRow(t('model.checkpoint'), t('model.eventsUnit', { n: cfg.checkpoint_interval }))}`;
  } catch {
    document.getElementById('llm-config').innerHTML = `<p class="text-sm text-error">${t('model.configFailed')}</p>`;
  }
}
