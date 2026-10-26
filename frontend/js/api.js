import { t } from './i18n.js';

export function apiBase() {
  return (typeof window !== 'undefined' && window.PRDS_API_BASE) || 'http://localhost:8000/api';
}

/** Odyssey backend origin (without /api), for LightRAG proxy iframe. */
export function apiOrigin() {
  const base = apiBase().replace(/\/$/, '');
  return base.replace(/\/api$/, '') || 'http://localhost:8000';
}

function url(path) {
  const base = apiBase().replace(/\/$/, '');
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${base}${p}`;
}

async function fetchJson(path, { timeoutMs = 15000, signal, ...init } = {}) {
  const ctrl = new AbortController();
  const abort = () => ctrl.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(abort, timeoutMs);
  try {
    const r = await fetch(url(path), { ...init, signal: ctrl.signal });
    if (!r.ok) {
      let detail = await r.text();
      try { detail = JSON.parse(detail).detail || detail; } catch (_) {}
      const error = new Error(detail);
      error.status = r.status;
      throw error;
    }
    return await r.json();
  } catch (e) {
    if (e?.name === 'AbortError' && !signal?.aborted) throw new Error(t('common.requestTimeout'));
    throw e;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'interrupted']);

export function issueLabel(issue) {
  if (!issue) return '';
  const key = `issue.${issue.code}`;
  const message = t(key) === key ? t('issue.stage_failed') : t(key);
  const phase = issue.stage ? ` · ${phaseLabel(issue.stage)}` : '';
  const branch = issue.branch_id ? ` · ${issue.branch_id}` : '';
  const event = issue.event_index ? ` · ${t('unit.eventNth', { n: issue.event_index })}` : '';
  return message + phase + branch + event;
}

export const API = {
  async health() {
    const r = await fetch(url('/health'));
    return r.json();
  },

  async getConfig() {
    const r = await fetch(url('/config'));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getLlmSettings() {
    const r = await fetch(url('/llm-settings'));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async saveLlmSettings(payload) {
    const r = await fetch(url('/llm-settings'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async listLlmModels() {
    const r = await fetch(url('/llm-models'));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async addLlmModel(payload) {
    const r = await fetch(url('/llm-models'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async deleteLlmModel(id) {
    const r = await fetch(url(`/llm-models/${encodeURIComponent(id)}`), { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async setDefaultLlmModel(modelId) {
    const r = await fetch(url('/llm-models/default'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async chatAnswer({ message, model_id, session_id }) {
    const r = await fetch(url('/chat/answer'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        model_id: model_id || null,
        session_id: session_id || null,
      }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async chatAnswerStream({ message, model_id, session_id, onMeta, onDelta, onDone, onError }) {
    const r = await fetch(url('/chat/answer/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        model_id: model_id || null,
        session_id: session_id || null,
      }),
    });
    if (!r.ok) {
      let detail = await r.text();
      try {
        const j = JSON.parse(detail);
        detail = j.detail || detail;
      } catch (_) { /* keep text */ }
      throw new Error(detail || `HTTP ${r.status}`);
    }
    if (!r.body) throw new Error('Streaming not supported');

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let sawDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        let event;
        try {
          event = JSON.parse(line);
        } catch {
          throw new Error('Invalid stream payload');
        }
        if (event.type === 'meta') {
          onMeta?.(event);
        } else if (event.type === 'delta') {
          onDelta?.(event.content || '');
        } else if (event.type === 'done') {
          sawDone = true;
          onDone?.(event);
        } else if (event.type === 'error') {
          const err = new Error(event.detail || 'LLM request failed');
          if (onError) onError(err);
          else throw err;
          return;
        }
      }
    }

    if (buffer.trim()) {
      let event;
      try {
        event = JSON.parse(buffer);
      } catch {
        throw new Error('Invalid stream payload');
      }
      if (event.type === 'meta') onMeta?.(event);
      else if (event.type === 'delta') onDelta?.(event.content || '');
      else if (event.type === 'done') {
        sawDone = true;
        onDone?.(event);
      } else if (event.type === 'error') {
        const err = new Error(event.detail || 'LLM request failed');
        if (onError) onError(err);
        else throw err;
        return;
      }
    }

    if (!sawDone) {
      throw new Error('Stream ended before completion');
    }
  },

  async listChatSessions(limit = 50) {
    return fetchJson(`/chat/sessions?limit=${limit}`);
  },

  async getChatSession(id) {
    const r = await fetch(url(`/chat/sessions/${encodeURIComponent(id)}`));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async createChatSession(payload = {}) {
    const r = await fetch(url('/chat/sessions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async deleteChatSession(id) {
    const r = await fetch(url(`/chat/sessions/${encodeURIComponent(id)}`), { method: 'DELETE' });
    if (!r.ok) {
      let detail = await r.text();
      try {
        const j = JSON.parse(detail);
        detail = j.detail || detail;
      } catch (_) { /* keep text */ }
      throw new Error(detail || `HTTP ${r.status}`);
    }
    return r.json();
  },

  async kbStatus() {
    const r = await fetch(url('/kb/status'));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async listKbCategories() {
    const r = await fetch(url('/kb/categories'));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async createKbCategory(payload) {
    const r = await fetch(url('/kb/categories'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async deleteKbCategory(id) {
    const r = await fetch(url(`/kb/categories/${encodeURIComponent(id)}`), { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async listKbDocuments(category) {
    const q = new URLSearchParams({ category });
    const r = await fetch(url(`/kb/documents?${q}`));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async uploadKbDocument(file, category) {
    const fd = new FormData();
    fd.append('file', file);
    const q = new URLSearchParams({ category });
    const r = await fetch(url(`/kb/documents?${q}`), { method: 'POST', body: fd });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async deleteKbDocument(id, category) {
    const q = new URLSearchParams({ category });
    const r = await fetch(url(`/kb/documents/${encodeURIComponent(id)}?${q}`), { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getKbDocumentContent(id, category) {
    const q = new URLSearchParams({ category });
    const r = await fetch(url(`/kb/documents/${encodeURIComponent(id)}/content?${q}`));
    if (!r.ok) {
      let detail = await r.text();
      try {
        const j = JSON.parse(detail);
        detail = j.detail || detail;
      } catch (_) { /* keep text */ }
      throw new Error(detail || `HTTP ${r.status}`);
    }
    return r;
  },

  async listSimulations(limit = 50) {
    return fetchJson(`/simulations?limit=${limit}`);
  },

  async deleteSimulation(id) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      timeoutMs: 35000,
    });
  },

  async createSimulation(payload) {
    const r = await fetch(url('/simulations'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getStatus(id, { signal } = {}) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}`, { timeoutMs: 10000, signal });
  },

  async cancelSimulation(id) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}/cancel`, { method: 'POST', timeoutMs: 15000 });
  },

  async retrySimulation(id, modelId = null) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}/retry`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(modelId ? { model_id: modelId } : {}),
    });
  },

  async getResult(id, { signal } = {}) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}/result`, { signal });
  },

  async getDecisions(id, limit = 10, { signal } = {}) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}/decisions?limit=${limit}`, { signal });
  },

  async getKnowledgeGraph(id) {
    const r = await fetch(url(`/simulations/${id}/knowledge-graph`));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async pauseSimulation(id) {
    const r = await fetch(url(`/simulations/${id}/pause`), { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async resumeSimulation(id) {
    const r = await fetch(url(`/simulations/${id}/resume`), { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getUserEvents(id, { signal } = {}) {
    return fetchJson(`/simulations/${encodeURIComponent(id)}/events`, { signal });
  },

  async addUserEvent(id, event) {
    const r = await fetch(url(`/simulations/${id}/events`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async clearUserEvents(id) {
    const r = await fetch(url(`/simulations/${id}/events`), { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  pollStatus(id, onUpdate, options = {}) {
    if (typeof options === 'number') options = { intervalMs: options };
    const { intervalMs = 1500, onConnection = () => {} } = options;
    let stopped = false, timer = null, controller = null, failures = 0, lastUpdated = null, busy = false;
    const tick = async () => {
      if (stopped || busy) return;
      busy = true;
      controller = new AbortController();
      let delay = intervalMs;
      try {
        const data = await API.getStatus(id, { signal: controller.signal });
        if (stopped) return;
        failures = 0;
        lastUpdated = new Date();
        await onUpdate(data);
        if (stopped) return;
        onConnection({ state: 'connected', lastUpdated });
        if (TERMINAL_STATUSES.has(data.status)) stopped = true;
      } catch (error) {
        if (stopped) return;
        failures += 1;
        const missing = error.status === 404;
        const exhausted = failures >= 5;
        onConnection({ state: missing ? 'missing' : exhausted ? 'disconnected' : 'retrying',
          lastUpdated, failures, error });
        if (missing || exhausted) stopped = true;
        delay = [3000, 6000, 12000, 24000, 30000][Math.min(failures - 1, 4)];
      } finally {
        busy = false;
        if (!stopped) timer = setTimeout(tick, delay);
      }
    };
    const stop = () => { stopped = true; clearTimeout(timer); controller?.abort(); };
    stop.reconnect = () => {
      if (busy) return;
      clearTimeout(timer); stopped = false; failures = 0; void tick();
    };
    void tick();
    return stop;
  },
};

export const DEFAULT_STRATEGY_COUNT = 4;
export const DEFAULT_EVENT_COUNT = 6;

export function buildPayload(form) {
  const prefs = (() => {
    try {
      return JSON.parse(localStorage.getItem('prds_prefs') || '{}');
    } catch {
      return {};
    }
  })();
  const toList = (v) => Array.isArray(v)
    ? v.map(s => String(s).trim()).filter(Boolean)
    : (v ? String(v).split('\n').map(s => s.trim()).filter(Boolean) : []);
  const kbCategoryIds = Array.isArray(form.kbCategoryIds)
    ? form.kbCategoryIds.map(String).filter(Boolean)
    : toList(form.kb_category_ids);
  return {
    current_state: {
      background: form.background || '',
      constraints: toList(form.constraints),
      risks: toList(form.risks),
      opportunities: toList(form.opportunities),
    },
    goal: {
      description: form.goal || '',
      success_metrics: form.success_metrics && typeof form.success_metrics === 'object'
        ? form.success_metrics
        : {},
    },
    config: {
      model_id: form.modelId || null,
      domain_id: 'startup',
      agent_count: Number(form.agentCount) || prefs.defaultAgentCount || DEFAULT_STRATEGY_COUNT,
      max_events: Number(form.maxEvents) || prefs.defaultMaxEvents || DEFAULT_EVENT_COUNT,
      seed: 42,
      kb_category_ids: kbCategoryIds,
    },
  };
}

export function resolveDomainId() {
  return 'startup';
}

/** Strategy chips carry free-form labels from the model; echo unknown keys as-is. */
export function actionLabel(action) {
  if (!action) return t('common.none');
  const key = typeof action === 'string' ? action : action.value || action;
  const label = t(`action.${key}`, {});
  return label !== `action.${key}` ? label : key;
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
    { key: 'intake', labelKey: 'phaseStep.intake' },
    { key: 'event_plan', labelKey: 'phaseStep.events' },
    { key: 'branch_fork', labelKey: 'phaseStep.fork' },
    { key: 'branch_sim', labelKey: 'phaseStep.branchSim' },
    { key: 'scoring', labelKey: 'phaseStep.scoring' },
    { key: 'synthesis', labelKey: 'phaseStep.converge' },
  ].map(s => ({ ...s, label: t(s.labelKey) }));
}

// Legacy exports for compatibility
export const PHASE_LABELS = new Proxy({}, { get: (_, k) => phaseLabel(k) });
export const STATUS_LABELS = new Proxy({}, { get: (_, k) => statusLabel(k) });
export const EVENT_CATEGORIES = new Proxy({}, { get: (_, k) => eventCategoryLabel(k) });
export const ACTION_LABELS = new Proxy({}, { get: (_, k) => actionLabel(k) });
export const PHASE_STEPS = getPhaseSteps();
