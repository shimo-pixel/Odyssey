import { t } from './i18n.js';

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function fmtNum(value, digits = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

export function fmtPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${Math.round(n * 100)}%`;
}

/** Trim trailing zeros so predicted metric values read like "83" not "83.0". */
export function fmtMetric(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const digits = Math.abs(n) >= 100 ? 0 : Math.abs(n) >= 1 ? 1 : 3;
  return String(Number(n.toFixed(digits)));
}

export function pickHighlightAgent(agents, championId) {
  if (!agents?.length) return null;
  return agents.find(a => a.agent_id === championId)
    || agents.find(a => a.rank === 1)
    || agents[0];
}

/** "数学 62 → 83 (+21)" for every metric the state prediction touched. */
export function renderMetricReadings(metrics, { compact = false } = {}) {
  const rows = (metrics || []).filter(m => m && m.name != null);
  if (!rows.length) return '';
  const items = rows.map((m) => {
    const delta = Number(m.value) - Number(m.previous);
    const trend = !Number.isFinite(delta) || Math.abs(delta) < 1e-9
      ? 'flat'
      : delta > 0 ? 'up' : 'down';
    const sign = delta > 0 ? '+' : '';
    const unit = m.unit ? `<span class="metric-reading-unit">${esc(m.unit)}</span>` : '';
    return `
      <div class="metric-reading" title="${esc(m.reason)}">
        <span class="metric-reading-name">${esc(m.name)}</span>
        <span class="metric-reading-flow">
          <span class="metric-reading-prev">${fmtMetric(m.previous)}</span>
          <span class="metric-reading-arrow" aria-hidden="true">→</span>
          <span class="metric-reading-value metric-reading-value--${trend}">${fmtMetric(m.value)}${unit}</span>
        </span>
        ${trend === 'flat' ? '' : `<span class="metric-reading-delta metric-reading-delta--${trend}">${sign}${fmtMetric(delta)}</span>`}
      </div>`;
  }).join('');
  return `
    <div class="metric-readings ${compact ? 'metric-readings--compact' : ''}">
      <div class="metric-readings-title">${t('results.stateMetrics')}</div>
      ${items}
    </div>`;
}

export function renderGoalStatusBlock(goalStatus, { compact = false } = {}) {
  const g = goalStatus || {};
  const progress = Number(g.progress);

  if (compact) {
    return `
      <div class="period-metrics period-metrics--compact period-metrics--goal">
        <span>${t('results.goalProgress')} <strong class="text-primary">${fmtPct(progress)}</strong></span>
      </div>`;
  }

  return `
    <div class="period-metrics period-metrics--goal">
      <div class="period-metrics-title">${t('results.goalStatus')}</div>
      <div class="goal-progress-bar" aria-hidden="true">
        <div class="goal-progress-fill" style="width:${Math.max(0, Math.min(100, progress * 100))}%"></div>
      </div>
      <div class="period-metrics-grid period-metrics-grid--goal">
        <div><span class="period-metrics-label">${t('results.goalProgress')}</span><span class="period-metrics-value text-primary">${fmtPct(progress)}</span></div>
      </div>
    </div>`;
}

/** State panel under a strategy card: predicted metrics + goal progress. */
export function renderStatePanel(metrics, goalStatus, { compact = false } = {}) {
  const readings = renderMetricReadings(metrics, { compact });
  const hasGoal = goalStatus?.progress != null;
  if (!readings && !hasGoal) return '';
  return `
    <div class="period-metrics-panel ${compact ? 'period-metrics-panel--compact' : ''}">
      ${readings}
      ${hasGoal ? renderGoalStatusBlock(goalStatus, { compact }) : ''}
    </div>`;
}
