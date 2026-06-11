import { t } from './i18n.js';
import { fmtPct, fmtNum } from './periodMetrics.js';
import { icon } from './icons.js';

function statCard(label, value, cls = '') {
  return `
    <div class="px-4 py-3 rounded-xl border border-outline-variant bg-white">
      <span class="text-[10px] uppercase font-bold text-on-surface-variant block">${label}</span>
      <span class="font-mono text-xl font-bold ${cls}">${value}</span>
    </div>`;
}

function bandBar(band) {
  const p10 = Math.max(0, Math.min(1, Number(band.p10)));
  const p25 = Math.max(0, Math.min(1, Number(band.p25)));
  const median = Math.max(0, Math.min(1, Number(band.median)));
  const p75 = Math.max(0, Math.min(1, Number(band.p75)));
  const p90 = Math.max(0, Math.min(1, Number(band.p90)));
  const pct = v => `${(v * 100).toFixed(1)}%`;
  return `
    <div class="dist-band" title="P10 ${pct(p10)} · P25 ${pct(p25)} · ${t('results.median')} ${pct(median)} · P75 ${pct(p75)} · P90 ${pct(p90)}">
      <div class="dist-band-track">
        <div class="dist-band-1090" style="left:${p10 * 100}%;width:${(p90 - p10) * 100}%"></div>
        <div class="dist-band-2575" style="left:${p25 * 100}%;width:${(p75 - p25) * 100}%"></div>
        <div class="dist-band-median" style="left:${median * 100}%"></div>
      </div>
    </div>`;
}

function metricBandRow(b) {
  const isRatio = (b.metric || '').includes('progress') || ['market_share', 'product_maturity'].includes(b.metric);
  const fmt = v => (isRatio ? fmtPct(v) : fmtNum(v, Math.abs(v) >= 100 ? 0 : 1));
  return `
    <div class="flex items-center justify-between gap-3 py-1.5 border-b border-outline-variant/40 text-sm">
      <span class="text-on-surface-variant">${b.label || b.metric}</span>
      <span class="font-mono"><strong class="text-primary">${fmt(b.median)}</strong>
        <span class="text-on-surface-variant text-xs">｜${fmt(b.p25)}–${fmt(b.p75)}</span></span>
    </div>`;
}

export function renderUncertaintySection(dist) {
  if (!dist || !dist.sample_size) return '';
  const gp = dist.goal_progress || {};
  const reasons = Object.entries(dist.elimination_reasons || {});

  return `
    <section class="mb-10">
      <div class="rounded-xl border border-tertiary/30 bg-tertiary/5 px-4 py-3 mb-4">
        <p class="text-sm font-medium text-on-surface">${t('results.assumptionBanner')}</p>
      </div>
      <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h2 class="text-sm font-medium flex items-center gap-2">
          ${icon('insights', 'icon icon--md text-primary')}
          ${t('results.uncertainty')}
        </h2>
        <span class="text-xs text-on-surface-variant">${t('results.uncertaintyHint', { n: dist.sample_size, r: dist.replications })}</span>
      </div>

      <div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
        ${statCard(t('results.achievedRate'), fmtPct(dist.achieved_rate), 'text-secondary')}
        ${statCard(t('results.successRate'), fmtPct(dist.success_rate), 'text-secondary')}
        ${statCard(t('results.nearRate'), fmtPct(dist.near_success_rate), 'text-primary')}
        ${statCard(t('results.elimRate'), fmtPct(dist.elimination_rate), 'text-error')}
        ${statCard(t('results.sampleSize'), dist.sample_size)}
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="glass-panel bg-white p-5 rounded-xl">
          <p class="text-sm font-bold mb-3">${t('results.goalProgressBand')}</p>
          ${bandBar(gp)}
          <div class="flex justify-between text-xs text-on-surface-variant mt-2 font-mono">
            <span>${t('results.median')}: <strong class="text-primary">${fmtPct(gp.median)}</strong></span>
            <span>${t('results.range2575')}: ${fmtPct(gp.p25)}–${fmtPct(gp.p75)}</span>
            <span>${t('results.range1090')}: ${fmtPct(gp.p10)}–${fmtPct(gp.p90)}</span>
          </div>
          ${(dist.metric_bands || []).length ? `
            <p class="text-sm font-bold mt-5 mb-2">${t('results.metricBands')}</p>
            ${dist.metric_bands.map(metricBandRow).join('')}` : ''}
        </div>

        <div class="glass-panel bg-white p-5 rounded-xl">
          <p class="text-sm font-bold mb-3">${t('results.elimReasons')}</p>
          ${reasons.length ? reasons.map(([reason, count]) => {
            const total = reasons.reduce((s, [, c]) => s + c, 0) || 1;
            const pct = (count / total) * 100;
            return `
              <div class="mb-2">
                <div class="flex justify-between text-xs mb-1">
                  <span class="text-on-surface-variant">${reason}</span>
                  <span class="font-mono">${count}</span>
                </div>
                <div class="h-1.5 bg-surface-variant rounded-full overflow-hidden">
                  <div class="h-full rounded-full" style="width:${pct}%;background:var(--g-red)"></div>
                </div>
              </div>`;
          }).join('') : `<p class="text-sm text-on-surface-variant">—</p>`}
        </div>
      </div>

      ${renderParamAssumptions(dist.param_assumptions || [])}
    </section>`;
}

function renderParamAssumptions(params) {
  if (!params.length) return '';
  const groups = {};
  for (const p of params) {
    (groups[p.group] = groups[p.group] || []).push(p);
  }
  const body = Object.entries(groups).map(([group, items]) => `
    <div class="mb-3">
      <p class="text-[11px] font-bold uppercase text-on-surface-variant tracking-wider mb-1">${group}</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
        ${items.map(p => `
          <div class="flex justify-between text-xs py-0.5 border-b border-outline-variant/30">
            <span class="text-on-surface-variant">${p.label}</span>
            <span class="font-mono text-on-surface">${p.value}</span>
          </div>`).join('')}
      </div>
    </div>`).join('');

  return `
    <div class="mt-5">
      <button type="button" id="toggle-params" class="text-sm font-medium text-primary flex items-center gap-1">
        ${icon('tune', 'icon icon--sm')}
        <span id="toggle-params-label">${t('results.showParams')}</span>
      </button>
      <div id="param-assumptions" class="glass-panel bg-white p-5 rounded-xl mt-3" hidden>
        <p class="text-xs text-on-surface-variant mb-3">${t('results.paramAssumptionsHint')}</p>
        ${body}
      </div>
    </div>`;
}

export function mountUncertaintyInteractions() {
  const btn = document.getElementById('toggle-params');
  const panel = document.getElementById('param-assumptions');
  const label = document.getElementById('toggle-params-label');
  if (!btn || !panel) return;
  btn.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    if (label) label.textContent = panel.hidden ? t('results.showParams') : t('results.hideParams');
  });
}
