import { t } from './i18n.js';

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

export function fmtCashFlow(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(1)}`;
}

export function pickHighlightAgent(agents, championId) {
  if (!agents?.length) return null;
  return agents.find(a => a.agent_id === championId)
    || agents.find(a => a.rank === 1)
    || agents[0];
}

export function metricGapLines(goalStatus, limit = 2) {
  const gaps = goalStatus?.metric_gaps || {};
  return Object.entries(gaps)
    .filter(([, gap]) => Number(gap) > 0.001)
    .slice(0, limit)
    .map(([key, gap]) => {
      const digits = gap >= 10 ? 0 : gap >= 1 ? 1 : 3;
      return `${key}: ${fmtNum(gap, digits)}`;
    });
}

export function renderFinancialsBlock(financials, { compact = false } = {}) {
  const f = financials || {};
  if (compact) {
    return `
      <div class="period-metrics period-metrics--compact">
        <span>${t('results.finExpense')} <strong>${fmtNum(f.total_expense)}</strong></span>
        <span class="period-metrics-sep">·</span>
        <span>${t('results.finRevenue')} <strong>${fmtNum(f.total_revenue)}</strong></span>
        <span class="period-metrics-sep">·</span>
        <span>${t('results.finNet')} <strong class="${Number(f.net_cash_flow) >= 0 ? 'text-secondary' : 'text-error'}">${fmtCashFlow(f.net_cash_flow)}</strong></span>
      </div>`;
  }
  return `
    <div class="period-metrics">
      <div class="period-metrics-title">${t('results.periodFinancials')}</div>
      <div class="period-metrics-grid">
        <div><span class="period-metrics-label">${t('results.finAction')}</span><span class="period-metrics-value">${fmtNum(f.action_expense)}</span></div>
        <div><span class="period-metrics-label">${t('results.finBurn')}</span><span class="period-metrics-value">${fmtNum(f.operating_burn)}</span></div>
        <div><span class="period-metrics-label">${t('results.finExpense')}</span><span class="period-metrics-value">${fmtNum(f.total_expense)}</span></div>
        <div><span class="period-metrics-label">${t('results.finRevenue')}</span><span class="period-metrics-value text-secondary">${fmtNum(f.total_revenue)}</span></div>
        <div><span class="period-metrics-label">${t('results.finNet')}</span><span class="period-metrics-value ${Number(f.net_cash_flow) >= 0 ? 'text-secondary' : 'text-error'}">${fmtCashFlow(f.net_cash_flow)}</span></div>
      </div>
    </div>`;
}

export function renderGoalStatusBlock(goalStatus, { compact = false } = {}) {
  const g = goalStatus || {};
  const progress = Number(g.progress);
  const distance = Number(g.distance);
  const gaps = metricGapLines(g, compact ? 2 : 4);

  if (compact) {
    return `
      <div class="period-metrics period-metrics--compact period-metrics--goal">
        <span>${t('results.goalProgress')} <strong class="text-primary">${fmtPct(progress)}</strong></span>
        <span class="period-metrics-sep">·</span>
        <span>${t('results.goalDistance')} <strong>${fmtPct(distance)}</strong></span>
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
        <div><span class="period-metrics-label">${t('results.goalDistance')}</span><span class="period-metrics-value">${fmtPct(distance)}</span></div>
      </div>
      ${gaps.length ? `<p class="period-metrics-gaps">${t('results.metricGaps')}: ${gaps.join(' · ')}</p>` : ''}
    </div>`;
}

export function renderPeriodMetricsPanel(financials, goalStatus, { compact = false } = {}) {
  const hasGoal = goalStatus?.progress != null;
  if (!financials && !hasGoal) {
    return '';
  }
  return `
    <div class="period-metrics-panel ${compact ? 'period-metrics-panel--compact' : ''}">
      ${renderFinancialsBlock(financials, { compact })}
      ${renderGoalStatusBlock(goalStatus, { compact })}
    </div>`;
}
