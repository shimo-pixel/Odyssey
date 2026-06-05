import { API, getActionLabels, phaseLabel } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';

function getPipeline() {
  return [
    { phase: 'ontology', icon: 'schema', titleKey: 'model.pipe.graphrag', descKey: 'model.pipe.graphragDesc' },
    { phase: 'world_init', icon: 'public', titleKey: 'model.pipe.world', descKey: 'model.pipe.worldDesc' },
    { phase: 'agent_spawn', icon: 'hub', titleKey: 'model.pipe.spawn', descKey: 'model.pipe.spawnDesc' },
    { phase: 'simulation', icon: 'sync', titleKey: 'model.pipe.loop', descKey: 'model.pipe.loopDesc' },
    { phase: 'scoring', icon: 'leaderboard', titleKey: 'model.pipe.scoring', descKey: 'model.pipe.scoringDesc' },
    { phase: 'trajectory', icon: 'timeline', titleKey: 'model.pipe.trajectory', descKey: 'model.pipe.trajectoryDesc' },
    { phase: 'counterfactual', icon: 'alt_route', titleKey: 'model.pipe.counterfactual', descKey: 'model.pipe.counterfactualDesc' },
    { phase: 'synthesis', icon: 'auto_awesome', titleKey: 'model.pipe.synthesis', descKey: 'model.pipe.synthesisDesc' },
  ];
}

export function renderModel() {
  const actions = getActionLabels();
  return pageShell(`
    <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20">
      <header class="mb-10">
        <span class="text-xs text-primary font-bold uppercase tracking-widest">${t('model.tag')}</span>
        <h1 class="text-3xl font-bold mt-2 text-on-surface">${t('model.title')}</h1>
        <p class="text-on-surface-variant mt-2 max-w-2xl leading-relaxed">${t('model.desc')}</p>
      </header>

      <section class="mb-12">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">account_tree</span>${t('model.pipeline')}
        </h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" id="pipeline-grid">
          ${getPipeline().map((p, i) => pipelineCard(p, i + 1)).join('')}
        </div>
      </section>

      <section class="mb-12 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="glass-panel p-6 rounded-xl">
          <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">psychology</span>${t('model.llmLayer')}
          </h2>
          <div id="llm-config" class="space-y-4">
            <div class="animate-pulse h-20 bg-surface-container rounded-lg"></div>
          </div>
        </div>
        <div class="glass-panel p-6 rounded-xl">
          <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
            <span class="material-symbols-outlined text-secondary">tune</span>${t('model.engineParams')}
          </h2>
          <div id="engine-config" class="space-y-3">
            <div class="animate-pulse h-20 bg-surface-container rounded-lg"></div>
          </div>
        </div>
      </section>

      <section class="mb-12">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-tertiary">touch_app</span>${t('model.actionSpace')}
        </h2>
        <p class="text-sm text-on-surface-variant mb-4">${t('model.actionSpaceDesc')}</p>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
          ${Object.entries(actions).map(([key, label]) => actionTile(key, label)).join('')}
        </div>
      </section>

      <section>
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">functions</span>${t('model.scoring')}
        </h2>
        <div class="glass-panel p-6 rounded-xl font-mono text-sm">
          <p class="text-on-surface mb-4">Score = GoalAchievement × 40% + ResourceEfficiency × 20% + RiskControl × 15% + ExecutionQuality × 15% + Adaptability × 10%</p>
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            ${scoreWeight(t('model.score.goal'), '40%', 'text-primary')}
            ${scoreWeight(t('model.score.efficiency'), '20%', 'text-secondary')}
            ${scoreWeight(t('model.score.risk'), '15%', 'text-tertiary')}
            ${scoreWeight(t('model.score.execution'), '15%', 'text-primary')}
            ${scoreWeight(t('model.score.adapt'), '10%', 'text-secondary')}
          </div>
        </div>
      </section>
    </div>
  `, { sidebarActive: 'model', mainClass: 'ml-60 min-h-screen bg-background' });
}

function pipelineCard(p, n) {
  const iconBgs = ['#e8f0fe', '#fef7e0', '#e6f4ea', '#f3e8fd', '#fce8e6', '#fef0e6', '#e8f0fe', '#f3e8fd'];
  const iconColors = ['#1a73e8', '#f9ab00', '#1e8e3e', '#9334e6', '#d93025', '#e8710a', '#1a73e8', '#9334e6'];
  const bg = iconBgs[(n - 1) % iconBgs.length];
  const color = iconColors[(n - 1) % iconColors.length];
  return `
    <div class="glass-panel p-4 hover:border-outline transition-colors cursor-default">
      <div class="flex items-center gap-2 mb-3">
        <span class="w-8 h-8 rounded-lg flex items-center justify-center" style="background:${bg}">
          <span class="material-symbols-outlined text-lg" style="color:${color}">${p.icon}</span>
        </span>
        <span class="font-mono text-xs text-on-surface-variant">0${n}</span>
      </div>
      <h3 class="font-medium text-sm text-on-surface">${t(p.titleKey)}</h3>
      <p class="text-xs text-on-surface-variant mt-1 leading-relaxed">${t(p.descKey)}</p>
      <span class="inline-block mt-2 text-[10px] font-mono text-outline">${phaseLabel(p.phase)}</span>
    </div>`;
}

function actionTile(key, label) {
  return `
    <div class="bg-surface-container-low border border-outline-variant rounded-lg p-3 text-center hover:border-primary/40 transition-colors">
      <span class="text-sm font-bold text-on-surface block">${label}</span>
      <span class="text-[10px] font-mono text-outline">${key}</span>
    </div>`;
}

function scoreWeight(name, pct, colorClass) {
  return `<div class="bg-surface-container-low rounded-lg p-3 text-center">
    <span class="${colorClass} font-bold block">${pct}</span>
    <span class="text-on-surface-variant">${name}</span>
  </div>`;
}

function configRow(label, value) {
  return `<div class="flex justify-between items-center py-2 border-b border-outline-variant/40 last:border-0">
    <span class="text-sm text-on-surface-variant">${label}</span>
    <span class="font-mono text-sm font-bold text-on-surface">${value}</span>
  </div>`;
}

export async function mountModel() {
  try {
    const cfg = await fetch('/config').then(r => r.json());
    document.getElementById('llm-config').innerHTML = `
      ${configRow(t('model.decisionModel'), cfg.llm_model)}
      ${configRow(t('model.analysisModel'), cfg.llm_model_analysis)}
      ${configRow(t('model.maxConcurrent'), cfg.max_concurrent_llm)}
      <div class="mt-3 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full ${cfg.llm_configured ? 'bg-secondary' : 'bg-tertiary'}"></span>
        <span class="text-xs text-on-surface-variant">${cfg.llm_configured ? t('model.apiOk') : t('model.apiMissing')}</span>
      </div>`;
    document.getElementById('engine-config').innerHTML = `
      ${configRow(t('model.defaultPaths'), cfg.default_agent_count)}
      ${configRow(t('model.defaultPeriods'), cfg.default_periods)}
      ${configRow(t('model.checkpoint'), t('model.periodsUnit', { n: cfg.checkpoint_interval }))}`;
  } catch {
    document.getElementById('llm-config').innerHTML = `<p class="text-sm text-error">${t('model.configFailed')}</p>`;
  }
}
