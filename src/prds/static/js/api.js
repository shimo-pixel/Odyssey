import { t } from './i18n.js';

export const API = {
  async health() {
    const r = await fetch('/health');
    return r.json();
  },

  async createSimulation(payload) {
    const r = await fetch('/simulations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async refineInput(payload) {
    const r = await fetch('/simulations/refine', {
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

export const DOMAIN_PROFILES = {
  startup: {
    id: 'startup',
    labelKey: 'domain.startup',
    resources: {
      cash: 100,
      team_size: 5,
      users: 0,
      revenue: 0,
      product_maturity: 0.3,
      brand_awareness: 0.2,
      market_share: 0.05,
      domain_metrics: {},
    },
    success_metrics: {},
    market_info: {
      tam: 1000,
      competition_intensity: 0.5,
      user_growth_rate: 0.05,
    },
    defaultMaxEvents: 6,
    defaultAgents: 10,
  },
};

export function buildPayload(form) {
  const profile = DOMAIN_PROFILES.startup;
  const toList = (v) => Array.isArray(v)
    ? v.map(s => String(s).trim()).filter(Boolean)
    : (v ? String(v).split('\n').map(s => s.trim()).filter(Boolean) : []);
  const constraints = toList(form.constraints);
  const metrics = form.success_metrics && typeof form.success_metrics === 'object'
    ? form.success_metrics
    : {};
  return {
    current_state: {
      background: form.background || '',
      resources: { ...profile.resources },
      constraints,
      market_info: { ...profile.market_info },
      risks: toList(form.risks),
      opportunities: toList(form.opportunities),
    },
    goal: {
      description: form.goal || '',
      success_metrics: metrics,
    },
    config: {
      domain_id: 'startup',
      agent_count: Number(form.agentCount) || profile.defaultAgents,
      max_events: Number(form.maxEvents) || profile.defaultMaxEvents,
      replications: Number(form.replications) || 1,
      seed: 42,
      checkpoint_interval: 2,
    },
  };
}

const ACTION_KEYS = [
  'hire', 'layoff', 'fundraise', 'product_dev', 'marketing',
  'strategic_pivot', 'partnership', 'acquisition', 'cost_cut', 'hold',
];

export function resolveDomainId() {
  return 'startup';
}

export function actionLabel(action) {
  if (!action) return t('common.none');
  const key = typeof action === 'string' ? action : action.value || action;
  const label = t(`action.${key}`, {});
  return label !== `action.${key}` ? label : key;
}

export function getActionLabels() {
  return Object.fromEntries(ACTION_KEYS.map(k => [k, t(`action.${k}`)]));
}

export function phaseLabel(phase) {
  return t(`phase.${phase}`, {}) !== `phase.${phase}` ? t(`phase.${phase}`) : phase;
}

export function statusLabel(status) {
  return t(`status.${status}`, {}) !== `status.${status}` ? t(`status.${status}`) : status;
}

export function eventCategoryLabel(cat) {
  return t(`event.${cat}`, {}) !== `event.${cat}` ? t(`event.${cat}`) : cat;
}

export function getEventCategories() {
  return {
    macro: t('event.macro'),
    market: t('event.market'),
    org: t('event.org'),
    resource: t('event.resource'),
  };
}

export function getPhaseSteps() {
  return [
    { key: 'ontology', labelKey: 'phaseStep.analysis' },
    { key: 'world_init', labelKey: 'phaseStep.goal' },
    { key: 'ontology', labelKey: 'phaseStep.ontology' },
    { key: 'world_init', labelKey: 'phaseStep.knowledge' },
    { key: 'agent_spawn', labelKey: 'phaseStep.spawn' },
    { key: 'synthesis', labelKey: 'phaseStep.converge' },
  ].map(s => ({ ...s, label: t(s.labelKey) }));
}

// Legacy exports for compatibility
export const PHASE_LABELS = new Proxy({}, { get: (_, k) => phaseLabel(k) });
export const STATUS_LABELS = new Proxy({}, { get: (_, k) => statusLabel(k) });
export const EVENT_CATEGORIES = new Proxy({}, { get: (_, k) => eventCategoryLabel(k) });
export const ACTION_LABELS = new Proxy({}, { get: (_, k) => actionLabel(k) });
export const PHASE_STEPS = getPhaseSteps();
