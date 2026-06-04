import { API, ACTION_LABELS, PHASE_LABELS, PHASE_STEPS } from '../api.js';
import { pageShell } from '../layout.js';

const PIPELINE = [
  { phase: 'ontology', icon: 'schema', title: 'GraphRAG 建模', desc: '分块抽取实体关系，生成世界背景' },
  { phase: 'world_init', icon: 'public', title: '世界初始化', desc: '构建共享初始 WorldState' },
  { phase: 'agent_spawn', icon: 'hub', title: '平行路径生成', desc: '相同初始条件下的 N 条路径' },
  { phase: 'simulation', icon: 'sync', title: '决策循环', desc: '注入事件 → 观察 → 选择 → 执行' },
  { phase: 'scoring', icon: 'leaderboard', title: '路径评分', desc: '目标达成、效率、风险控制' },
  { phase: 'trajectory', icon: 'timeline', title: '轨迹提取', desc: '记录逐步决策链' },
  { phase: 'counterfactual', icon: 'alt_route', title: '反事实分析', desc: '关键节点的备选选择对比' },
  { phase: 'synthesis', icon: 'auto_awesome', title: '路径收敛', desc: '提炼最优决策序列' },
];

export function renderModel() {
  return pageShell(`
    <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20">
      <header class="mb-10">
        <span class="text-xs text-primary font-bold uppercase tracking-widest">PRDS Engine</span>
        <h1 class="text-3xl font-bold mt-2 text-on-surface">推演模型</h1>
        <p class="text-on-surface-variant mt-2 max-w-2xl leading-relaxed">
          平行现实决策模拟器的核心架构。所有路径共享同一初始世界，在随机事件下独立做出选择，最终收敛为最优决策序列。
        </p>
      </header>

      <section class="mb-12">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">account_tree</span>推演流水线
        </h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" id="pipeline-grid">
          ${PIPELINE.map((p, i) => pipelineCard(p, i + 1)).join('')}
        </div>
      </section>

      <section class="mb-12 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="glass-panel bg-white p-6 rounded-xl">
          <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">psychology</span>LLM 模型层
          </h2>
          <div id="llm-config" class="space-y-4">
            <div class="animate-pulse h-20 bg-surface-container rounded-lg"></div>
          </div>
        </div>
        <div class="glass-panel bg-white p-6 rounded-xl">
          <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
            <span class="material-symbols-outlined text-secondary">tune</span>引擎参数
          </h2>
          <div id="engine-config" class="space-y-3">
            <div class="animate-pulse h-20 bg-surface-container rounded-lg"></div>
          </div>
        </div>
      </section>

      <section class="mb-12">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-tertiary">touch_app</span>决策动作空间
        </h2>
        <p class="text-sm text-on-surface-variant mb-4">每条路径在每个周期从以下动作中选择一项（由 LLM 决策，规则引擎计算结果）</p>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
          ${Object.entries(ACTION_LABELS).map(([key, label]) => actionTile(key, label)).join('')}
        </div>
      </section>

      <section>
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">functions</span>路径评分公式
        </h2>
        <div class="glass-panel bg-white p-6 rounded-xl font-mono text-sm">
          <p class="text-on-surface mb-4">Score = GoalAchievement × 40% + ResourceEfficiency × 20% + RiskControl × 15% + ExecutionQuality × 15% + Adaptability × 10%</p>
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            ${scoreWeight('目标达成', '40%', 'text-primary')}
            ${scoreWeight('资源效率', '20%', 'text-secondary')}
            ${scoreWeight('风险控制', '15%', 'text-tertiary')}
            ${scoreWeight('执行质量', '15%', 'text-primary')}
            ${scoreWeight('适应性', '10%', 'text-secondary')}
          </div>
        </div>
      </section>
    </div>
  `, { topNav: 'model', noSidebar: true, mainClass: 'mt-16 min-h-screen' });
}

function pipelineCard(p, n) {
  return `
    <div class="glass-panel bg-white p-4 rounded-xl hover:border-primary/30 transition-colors">
      <div class="flex items-center gap-2 mb-2">
        <span class="font-mono text-xs font-bold text-primary">0${n}</span>
        <span class="material-symbols-outlined text-primary text-lg">${p.icon}</span>
      </div>
      <h3 class="font-bold text-sm text-on-surface">${p.title}</h3>
      <p class="text-xs text-on-surface-variant mt-1 leading-relaxed">${p.desc}</p>
      <span class="inline-block mt-2 text-[10px] font-mono text-outline">${PHASE_LABELS[p.phase] || p.phase}</span>
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
      ${configRow('决策模型', cfg.llm_model)}
      ${configRow('分析模型', cfg.llm_model_analysis)}
      ${configRow('最大并发', cfg.max_concurrent_llm)}
      <div class="mt-3 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full ${cfg.llm_configured ? 'bg-secondary' : 'bg-tertiary'}"></span>
        <span class="text-xs text-on-surface-variant">${cfg.llm_configured ? 'API Key 已配置' : '未配置 · 将使用 Mock 模式'}</span>
      </div>`;
    document.getElementById('engine-config').innerHTML = `
      ${configRow('默认平行路径', cfg.default_agent_count)}
      ${configRow('默认推演周期', cfg.default_periods)}
      ${configRow('Checkpoint 间隔', cfg.checkpoint_interval + ' 周期')}`;
  } catch {
    document.getElementById('llm-config').innerHTML = '<p class="text-sm text-error">无法加载配置</p>';
  }
}
