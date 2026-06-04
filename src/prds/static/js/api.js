export const API = {
  async health() {
    const r = await fetch('/health');
    return r.json();
  },

  async createSimulation(payload, useMock = true) {
    const r = await fetch(`/simulations?use_mock=${useMock}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getStatus(id) {
    const r = await fetch(`/simulations/${id}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getResult(id) {
    const r = await fetch(`/simulations/${id}/result`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getDecisions(id, limit = 10) {
    const r = await fetch(`/simulations/${id}/decisions?limit=${limit}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getKnowledgeGraph(id) {
    const r = await fetch(`/simulations/${id}/knowledge-graph`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async pauseSimulation(id) {
    const r = await fetch(`/simulations/${id}/pause`, { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async resumeSimulation(id) {
    const r = await fetch(`/simulations/${id}/resume`, { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getUserEvents(id) {
    const r = await fetch(`/simulations/${id}/events`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async addUserEvent(id, event) {
    const r = await fetch(`/simulations/${id}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async clearUserEvents(id) {
    const r = await fetch(`/simulations/${id}/events`, { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  pollStatus(id, onUpdate, intervalMs = 1500) {
    const timer = setInterval(async () => {
      try {
        const data = await API.getStatus(id);
        onUpdate(data);
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(timer);
        }
      } catch (e) {
        console.error(e);
      }
    }, intervalMs);
    return () => clearInterval(timer);
  },
};

export function buildPayload(form) {
  const constraints = form.constraints
    ? form.constraints.split('\n').map(s => s.trim()).filter(Boolean)
    : [];
  return {
    current_state: {
      background: form.background || '',
      resources: {
        cash: 100,
        team_size: 5,
        users: 0,
        revenue: 0,
        product_maturity: 0.3,
        brand_awareness: 0.2,
        market_share: 0.05,
      },
      constraints,
      market_info: {
        tam: 1000,
        competition_intensity: 0.5,
        user_growth_rate: 0.05,
      },
      risks: [],
      opportunities: [],
    },
    goal: {
      description: form.goal || '',
      success_metrics: {},
    },
    config: {
      agent_count: Number(form.agentCount) || 10,
      periods: Number(form.periods) || 6,
      period_time_unit: form.periodTimeUnit || 'month',
      period_time_length: Number(form.periodTimeLength) || 1,
      simulation_start_date: form.simulationStartDate ? form.simulationStartDate : null,
      seed: 42,
      checkpoint_interval: 2,
    },
  };
}

export const ACTION_LABELS = {
  hire: '招聘',
  layoff: '裁员',
  fundraise: '融资',
  product_dev: '产品开发',
  marketing: '市场推广',
  strategic_pivot: '战略转型',
  partnership: '合作',
  acquisition: '并购',
  cost_cut: '削减成本',
  hold: '观望',
};

export function actionLabel(action) {
  if (!action) return '—';
  const key = typeof action === 'string' ? action : action.value || action;
  return ACTION_LABELS[key] || key;
}

export const PHASE_LABELS = {
  pending: '等待中',
  ontology: '本体建模',
  world_init: '世界初始化',
  agent_spawn: '智能体生成',
  simulation: '决策推演',
  scoring: '评分排名',
  trajectory: '轨迹生成',
  counterfactual: '反事实分析',
  synthesis: '策略提炼',
  completed: '已完成',
  failed: '失败',
};

export const STATUS_LABELS = {
  pending: '等待中',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
};

export const EVENT_CATEGORIES = {
  macro: '宏观环境',
  market: '市场',
  org: '组织',
  resource: '资源',
};

export const PHASE_STEPS = [
  { key: 'ontology', label: '现状分析' },
  { key: 'world_init', label: '目标定义' },
  { key: 'ontology', label: '本体建模' },
  { key: 'world_init', label: '知识图谱' },
  { key: 'agent_spawn', label: '平行世界生成' },
  { key: 'synthesis', label: '路径收敛' },
];
