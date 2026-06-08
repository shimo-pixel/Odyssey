import { API, actionLabel, resolveDomainId } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import {
  pickHighlightAgent,
  renderFinancialsBlock,
  renderGoalStatusBlock,
  renderPeriodMetricsPanel,
} from '../periodMetrics.js';
import { renderUncertaintySection, mountUncertaintyInteractions } from '../distribution.js';
import { formatPeriodLabel, formatPeriodShort, timeConfigFrom, unitLengthLabel } from '../time.js';

const PATH_FETCH_LIMIT = 25;
const MATRIX_COL_LIMIT = 12;

export function renderResults(simId) {
  return pageShell(`
    <div class="p-6 lg:p-10 max-w-[1400px] mx-auto" id="results-root">
      <div class="flex items-center justify-center py-24">
        <div class="animate-pulse text-primary font-bold">${t('results.loading')}</div>
      </div>
    </div>
  `, { sidebarActive: 'results', simId });
}

export async function mountResults(simId) {
  const root = document.getElementById('results-root');
  try {
    const [result, decisions] = await Promise.all([
      API.getResult(simId),
      API.getDecisions(simId, PATH_FETCH_LIMIT).catch(() => ({ paths: [], period_comparisons: [] })),
    ]);
    const paths = decisions.paths?.length ? decisions.paths : result.agent_paths || [];
    const periodComparisons = decisions.period_comparisons?.length
      ? decisions.period_comparisons
      : result.period_comparisons?.length
        ? result.period_comparisons
        : buildPeriodComparisonsFromPaths(paths);
    const timeConfig = timeConfigFrom(
      decisions.time_config || {
        period_time_unit: result.period_time_unit,
        period_time_length: result.period_time_length,
        simulation_start_date: result.simulation_start_date,
      },
    );
    const eventItems = flattenEventItems(periodComparisons, timeConfig);

    const domainId = resolveDomainId(result, decisions);
    root.innerHTML = buildResultsHTML(result, paths, periodComparisons, eventItems, timeConfig, domainId);
    mountInteractions(eventItems, periodComparisons, result.champion_agent_id, timeConfig, domainId);
    mountUncertaintyInteractions();
  } catch (e) {
    root.innerHTML = `<div class="glass-panel p-8 text-center"><p class="text-error font-bold">${t('results.loadFailed')}</p>
      <p class="text-sm text-on-surface-variant mt-2">${escapeHtml(e.message)}</p>
      <a href="#monitor/${simId}" class="inline-block mt-4 text-primary font-bold">${t('common.backMonitor')}</a></div>`;
  }
}

function periodLabel(period, timeConfig, periodData) {
  if (periodData?.period_label) return periodData.period_label;
  return formatPeriodLabel(period, timeConfig);
}

function flattenEventItems(periodComparisons, timeConfig) {
  const items = [];
  for (const period of periodComparisons) {
    const summaries = period.event_summaries?.length
      ? period.event_summaries
      : (period.events || []).map(t => ({ event_type: t, description: formatEventType(t), impact: 0 }));

    if (!summaries.length) {
      items.push({
        id: `period-${period.period}`,
        period: period.period,
        event: { event_type: 'world_update', description: period.world_summary || periodLabel(period.period, timeConfig, period), impact: 0 },
        periodData: period,
      });
      continue;
    }

    summaries.forEach((ev, idx) => {
      items.push({
        id: `period-${period.period}-event-${idx}`,
        period: period.period,
        event: ev,
        periodData: period,
      });
    });
  }
  return items;
}

function buildPeriodComparisonsFromPaths(paths) {
  const periods = [...new Set(paths.flatMap(p => (p.steps || []).map(s => s.period)))].sort((a, b) => a - b);
  return periods.map(period => {
    let ref = null;
    const agents = [];
    for (const path of paths) {
      const step = path.steps?.find(s => s.period === period);
      if (!step) continue;
      if (!ref) ref = step;
      agents.push({
        agent_id: path.agent_id,
        rank: path.rank,
        action: step.action,
        decision: step.decision,
        reasoning: step.reasoning,
        outcome: step.outcome,
        success: step.success,
        financials: step.financials,
        period_summary: step.period_summary,
        goal_status: step.goal_status,
      });
    }
    agents.sort((a, b) => a.rank - b.rank);
    return {
      period,
      world_summary: ref?.world_summary || '',
      events: ref?.events || [],
      event_summaries: (ref?.events || []).map(t => ({ event_type: t, description: formatEventType(t), impact: 0 })),
      agents,
    };
  });
}

function buildResultsHTML(r, paths, periodComparisons, eventItems, timeConfig, domainId = 'startup') {
  const championId = r.champion_agent_id;
  const periods = periodComparisons.length || maxPeriods(paths);
    const totalAgents = periodComparisons.reduce(
      (max, p) => Math.max(max, p.agents?.length || 0),
      0,
    ) || paths.length;

  return `
    <header class="mb-8">
      <span class="text-xs text-primary font-bold uppercase tracking-widest">${t('results.tag')}</span>
      <h1 class="text-2xl lg:text-3xl font-bold mt-2 text-on-surface">${t('results.title')}</h1>
      <p class="text-sm text-on-surface-variant mt-2 max-w-2xl">
        ${t('results.desc', { n: totalAgents || r.agent_count })}
      </p>
      <div class="flex flex-wrap gap-4 mt-4">
        <statChip label="${t('results.stat.agents')}" value="${r.agent_count}" />
        <statChip label="${t('results.stat.steps')}" value="${r.periods_simulated}" />
        <statChip label="${t('results.stat.granularity')}" value="${unitLengthLabel(timeConfig.period_time_unit, timeConfig.period_time_length)}" />
        <statChip label="${t('results.stat.events')}" value="${eventItems.length}" />
        <statChip label="${t('results.stat.best')}" value="#${paths.find(p => p.agent_id === championId)?.rank || 1}" highlight />
      </div>
      ${totalAgents > 1 ? '' : `
        <p class="text-xs text-tertiary mt-3 bg-tertiary/10 border border-tertiary/20 rounded-lg px-3 py-2 inline-block">
          ${t('results.multiAgentWarn')}
        </p>`}
    </header>

    ${renderUncertaintySection(r.outcome_distribution)}

    ${renderResearchSection(r.world_background)}

    <section class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">table_chart</span>
          ${t('results.overview')}
        </h2>
        <span class="text-xs text-on-surface-variant">${t('results.overviewHint', { n: Math.min(paths.length, MATRIX_COL_LIMIT) })}</span>
      </div>
      <div class="glass-panel bg-white rounded-xl overflow-hidden">
        ${buildDecisionMatrix(paths, periods, championId, periodComparisons, timeConfig, domainId)}
      </div>
    </section>

    <section class="mb-10 grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div class="lg:col-span-4 xl:col-span-3">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-bold flex items-center gap-2">
            <span class="material-symbols-outlined text-tertiary">bolt</span>
            ${t('results.eventList')}
          </h2>
          <span class="text-[10px] font-bold text-on-surface-variant">${t('results.eventCount', { n: eventItems.length })}</span>
        </div>
        <div id="event-list" class="space-y-2 max-h-[620px] overflow-y-auto custom-scrollbar pr-1">
          ${eventItems.length
            ? eventItems.map(item => eventListItem(item, timeConfig, championId, domainId)).join('')
            : `<p class="text-sm text-on-surface-variant p-4">${t('results.noEvents')}</p>`}
        </div>
      </div>
      <div class="lg:col-span-8 xl:col-span-9">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">groups</span>
          ${t('results.agentDetail')}
        </h2>
        <div id="event-detail-header" class="glass-panel px-5 py-4 mb-4 rounded-xl hidden"></div>
        <div id="event-detail" class="space-y-3 max-h-[640px] overflow-y-auto custom-scrollbar pr-1">
          <p class="text-sm text-on-surface-variant glass-panel p-6 rounded-xl">${t('results.selectEvent')}</p>
        </div>
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
        <span class="material-symbols-outlined text-tertiary">alt_route</span>
        ${t('results.counterfactual')}
      </h2>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        ${(r.counterfactuals || []).map(cf => counterfactualCard(cf)).join('') || `<p class="text-on-surface-variant text-sm">${t('results.noCounterfactual')}</p>`}
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-bold mb-2 flex items-center gap-2">
        <span class="material-symbols-outlined text-primary">map</span>
        ${t('results.roadmap')}
      </h2>
      <p class="text-xs text-on-surface-variant mb-4">${escapeHtml(r.synthesis?.disclaimer || '')}</p>
      <div class="space-y-2">
        ${(r.synthesis?.recommended_roadmap || []).map((step, i) => roadmapItem(step, i + 1)).join('')}
      </div>
    </section>`;
}

function researchProviderLabel(key) {
  const labels = {
    deep_research: 'Gemini Deep Research',
    grounded: 'Gemini + Search',
    fallback: t('research.providerFallback'),
    off: t('research.providerOff'),
  };
  return labels[key] || key || '';
}

function renderResearchSection(wb) {
  const report = (wb?.research_report || '').trim();
  if (!report) return '';
  const provider = researchProviderLabel(wb.research_provider);
  const citations = wb.research_citations || [];
  return `
    <section class="mb-10">
      <details class="glass-panel bg-white rounded-xl overflow-hidden">
        <summary class="flex items-center justify-between gap-2 px-5 py-4 cursor-pointer select-none">
          <span class="text-lg font-bold flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">travel_explore</span>
            ${t('research.title')}
          </span>
          <span class="text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/10 px-2 py-0.5 rounded-full">${escapeHtml(provider)}</span>
        </summary>
        <div class="px-5 pb-5">
          <p class="text-xs text-on-surface-variant mb-3">${t('research.hint')}</p>
          <div class="research-report custom-scrollbar">${escapeHtml(report)}</div>
          ${citations.length ? `
            <div class="mt-4">
              <p class="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant mb-2">${t('research.sources')}</p>
              <ol class="research-citations">
                ${citations.slice(0, 20).map(c => `<li><a href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(c.title || c.url)}</a></li>`).join('')}
              </ol>
            </div>` : ''}
        </div>
      </details>
    </section>`;
}

function statChip(label, value, highlight = false) {
  return `<div class="px-4 py-2 rounded-lg border ${highlight ? 'border-primary bg-primary/5' : 'border-outline-variant bg-white'}">
    <span class="text-[10px] uppercase font-bold text-on-surface-variant block">${label}</span>
    <span class="font-mono text-lg font-bold ${highlight ? 'text-primary' : 'text-on-surface'}">${value}</span>
  </div>`;
}

function maxPeriods(paths) {
  return Math.max(0, ...paths.map(p => p.steps?.length || 0));
}

function formatEventType(type) {
  return String(type || '').replace(/_/g, ' ');
}

function impactLabel(impact) {
  if (impact >= 0.3) return { text: t('common.positive'), cls: 'text-secondary' };
  if (impact <= -0.3) return { text: t('common.negative'), cls: 'text-error' };
  return { text: t('common.neutral'), cls: 'text-on-surface-variant' };
}

function eventListItem(item, timeConfig, championId, domainId = 'startup') {
  const ev = item.event;
  const impact = impactLabel(ev.impact || 0);
  const agentCount = item.periodData?.agents?.length || 0;
  const highlight = pickHighlightAgent(item.periodData?.agents, championId);
  const metrics = highlight
    ? renderPeriodMetricsPanel(highlight.financials, highlight.goal_status, {
      compact: true,
      domainId,
      periodSummary: highlight.period_summary,
    })
    : '';
  return `
    <button type="button" data-event-id="${item.id}" data-period="${item.period}"
      class="event-item w-full text-left p-3.5 rounded-xl border border-outline-variant bg-white hover:border-primary/40 transition-all">
      <div class="flex items-center gap-2 mb-1.5 flex-wrap">
        <span class="font-mono text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded">${formatPeriodShort(item.period, timeConfig).split(' · ')[0]}</span>
        <span class="font-mono text-[10px] text-on-surface-variant">T${item.period}</span>
        <span class="text-[10px] font-bold ${impact.cls}">${impact.text}</span>
      </div>
      <p class="text-sm font-bold text-on-surface leading-snug">${escapeHtml(ev.description || formatEventType(ev.event_type))}</p>
      <p class="text-[10px] text-on-surface-variant font-mono mt-1">${escapeHtml(ev.event_type)}</p>
      ${metrics ? `<div class="mt-2">${metrics}</div>` : ''}
      <p class="text-[11px] text-on-surface-variant mt-2">${t('results.agentsRespond', { n: agentCount })}</p>
    </button>`;
}

function renderEventHeader(item, timeConfig, championId, domainId = 'startup') {
  const period = item.periodData;
  const ev = item.event;
  const impact = impactLabel(ev.impact || 0);
  const label = periodLabel(item.period, timeConfig, period);
  const highlight = pickHighlightAgent(period.agents, championId);
  return `
    <div>
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <span class="font-mono font-bold text-primary">${label}</span>
        <span class="text-xs font-bold ${impact.cls}">${impact.text}</span>
        <span class="text-xs text-on-surface-variant">${t('results.agentsRespond', { n: period.agents?.length || 0 })}</span>
      </div>
      <h3 class="font-bold text-lg text-on-surface">${escapeHtml(ev.description || formatEventType(ev.event_type))}</h3>
      <p class="text-xs font-mono text-on-surface-variant mt-1">${escapeHtml(ev.event_type)}</p>
    </div>
    ${highlight ? renderPeriodMetricsPanel(highlight.financials, highlight.goal_status, { domainId, periodSummary: highlight.period_summary }) : ''}
    <div class="mt-4 text-xs bg-surface-container-low rounded-lg p-3">
      <span class="font-bold text-on-surface block mb-1">${t('results.worldConditions')}</span>
      <p class="text-on-surface-variant leading-relaxed">${escapeHtml(period.world_summary || t('common.none'))}</p>
      ${(period.events || []).length > 1 ? `
        <p class="text-on-surface-variant mt-2">${t('results.otherEvents', { events: escapeHtml(period.events.filter(evt => evt !== ev.event_type).join(', ') || t('common.none')) })}</p>` : ''}
    </div>`;
}

function renderAgentResponses(period, championId, domainId = 'startup') {
  const agents = period.agents || [];
  if (!agents.length) {
    return `<p class="text-sm text-on-surface-variant glass-panel p-6 rounded-xl">${t('results.noAgentData')}</p>`;
  }

  const header = `
    <div class="flex items-center justify-between glass-panel bg-white px-4 py-3 rounded-xl mb-1 sticky top-0 z-10">
      <span class="text-sm font-bold text-on-surface">${t('results.agentCount', { n: agents.length })}</span>
      <span class="text-[10px] text-on-surface-variant">${t('results.agentHint')}</span>
    </div>`;

  const cards = agents.map(agent => {
    const ok = agent.success !== false;
    const isChampion = agent.agent_id === championId;
    const metrics = (agent.financials || agent.goal_status || agent.period_summary)
      ? `
        <div class="mt-3 pt-3 border-t border-outline-variant/60">
          ${renderPeriodMetricsPanel(agent.financials, agent.goal_status, { domainId, periodSummary: agent.period_summary })}
        </div>`
      : '';
    return `
      <article class="agent-decision-card p-4 rounded-xl border ${isChampion ? 'border-primary bg-primary/5' : 'border-outline-variant bg-white'}">
        <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div class="flex items-center gap-2 flex-wrap">
            ${agent.rank ? `<span class="font-mono text-xs font-bold ${isChampion ? 'text-primary' : 'text-on-surface'}">#${agent.rank}</span>` : ''}
            ${isChampion ? `<span class="text-[9px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-full">${t('common.champion')}</span>` : ''}
            <span class="text-[10px] font-mono text-on-surface-variant">${agent.agent_id.slice(0, 16)}…</span>
          </div>
          <span class="action-chip ${ok ? 'action-chip-ok' : 'action-chip-fail'}">${actionLabel(agent.action, domainId)}</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div class="bg-surface-container-low/80 rounded-lg p-3">
            <span class="text-[10px] font-bold uppercase text-on-surface-variant tracking-wider">${t('results.response')}</span>
            <p class="text-on-surface font-medium mt-1 leading-snug">${escapeHtml(agent.decision || '—')}</p>
            ${agent.reasoning ? `<p class="text-xs text-on-surface-variant mt-2 leading-relaxed">${escapeHtml(agent.reasoning)}</p>` : ''}
          </div>
          <div class="rounded-lg p-3 ${ok ? 'bg-secondary/5 border border-secondary/15' : 'bg-error/5 border border-error/15'}">
            <span class="text-[10px] font-bold uppercase ${ok ? 'text-secondary' : 'text-error'} tracking-wider">${t('results.outcome')}</span>
            <p class="text-xs ${ok ? 'text-secondary' : 'text-error'} mt-1 leading-relaxed font-medium">${escapeHtml(agent.outcome || (ok ? t('common.success') : t('common.failed')))}</p>
          </div>
        </div>
        ${metrics}
      </article>`;
  }).join('');

  return header + cards;
}

const ACTION_COLOR = {
  product_dev: 'blue',
  marketing: 'orange',
  hire: 'teal',
  partnership: 'green',
  fundraise: 'purple',
  acquisition: 'pink',
  strategic_pivot: 'yellow',
  layoff: 'red',
  cost_cut: 'red',
  hold: 'gray',
};

function actionColorKey(action) {
  const key = typeof action === 'string' ? action : action?.value || action;
  return ACTION_COLOR[key] || 'gray';
}

function progressTone(pct) {
  if (pct < 34) return 'low';
  if (pct < 67) return 'mid';
  return 'high';
}

function dmxProgressBar(goalStatus) {
  if (goalStatus?.progress == null) return '';
  const pct = Math.max(0, Math.min(100, Math.round(goalStatus.progress * 100)));
  return `
    <div class="dmx-prog" title="${t('results.goalProgress')}: ${pct}%">
      <div class="dmx-prog__track"><div class="dmx-prog__fill dmx-prog__fill--${progressTone(pct)}" style="width:${pct}%"></div></div>
      <span class="dmx-prog__pct">${pct}%</span>
    </div>`;
}

function dmxChip(action, ok, domainId) {
  return `<span class="dmx-chip ${ok ? '' : 'dmx-chip--fail'}" data-c="${actionColorKey(action)}">
    <span class="dmx-chip__dot"></span>${escapeHtml(actionLabel(action, domainId))}
  </span>`;
}

function dmxLegend() {
  return `
    <div class="dmx-legend">
      <span class="dmx-legend__item"><span class="dmx-legend__dot" style="background:var(--g-blue)"></span>${t('results.legendColor')}</span>
      <span class="dmx-legend__item"><span class="dmx-chip dmx-chip--fail" style="padding:0;width:14px;height:14px"></span>${t('results.legendFail')}</span>
      <span class="dmx-legend__item"><span class="dmx-legend__dot" style="background:var(--g-green)"></span>${t('results.legendProgress')}</span>
    </div>`;
}

function buildDecisionMatrix(paths, periods, championId, periodComparisons, timeConfig, domainId = 'startup') {
  const periodCount = typeof periods === 'number'
    ? periods
    : Math.max(periodComparisons.length, maxPeriods(paths));

  if (!paths.length && !periodComparisons.length) {
    return `<p class="p-6 text-sm text-on-surface-variant">${t('results.noData')}</p>`;
  }

  const cols = paths.slice(0, MATRIX_COL_LIMIT);
  const header = `
    <thead><tr>
      <th class="dmx-col-time text-left text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">${t('results.timeNode')}</th>
      <th class="dmx-world text-left text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">${t('results.eventCol')}</th>
      ${cols.map(p => {
        const champ = p.agent_id === championId;
        return `<th class="dmx-agent ${champ ? 'dmx-col-champ' : ''}">
          <div class="dmx-agent__rank">#${p.rank}</div>
          ${champ ? `<span class="dmx-agent__tag">${t('common.champion')}</span>` : ''}
        </th>`;
      }).join('')}
    </tr></thead>`;

  let rows = '';
  for (let period = 1; period <= periodCount; period++) {
    const periodData = periodComparisons.find(p => p.period === period);
    const refStep = cols[0]?.steps?.find(s => s.period === period);
    const eventTags = (periodData?.events?.slice(0, 3) || refStep?.events?.slice(0, 3) || [])
      .map(e => `<span class="dmx-tag">${escapeHtml(formatEventType(e))}</span>`).join('');
    const world = periodData?.world_summary?.slice(0, 72) || refStep?.world_summary?.slice(0, 72) || '—';

    rows += `<tr>
      <td class="dmx-col-time">
        <span class="dmx-period__badge">${formatPeriodShort(period, timeConfig).split(' · ')[0]}</span>
        <span class="dmx-period__t">T${period}</span>
      </td>
      <td class="dmx-world">
        <p class="dmx-world__text">${escapeHtml(world)}</p>
        ${eventTags ? `<div class="dmx-tags">${eventTags}</div>` : ''}
      </td>
      ${cols.map(p => {
        const step = p.steps?.find(s => s.period === period);
        const champ = p.agent_id === championId;
        if (!step) return `<td class="dmx-cell dmx-cell--empty ${champ ? 'dmx-col-champ' : ''}">—</td>`;
        const ok = step.success !== false;
        return `<td class="dmx-cell ${champ ? 'dmx-col-champ' : ''}">
          ${dmxChip(step.action, ok, domainId)}
          ${dmxProgressBar(step.goal_status)}
        </td>`;
      }).join('')}
    </tr>`;
  }

  return `<div class="dmx-wrap"><table class="dmx">${header}<tbody>${rows}</tbody></table></div>${dmxLegend()}`;
}

function mountInteractions(eventItems, periodComparisons, championId, timeConfig, domainId = 'startup') {
  const header = document.getElementById('event-detail-header');
  const detail = document.getElementById('event-detail');
  const items = document.querySelectorAll('.event-item');
  let selectedId = eventItems[0]?.id;

  function select(id) {
    selectedId = id;
    const item = eventItems.find(e => e.id === id);
    if (!item) return;

    items.forEach(el => {
      const active = el.dataset.eventId === id;
      el.classList.toggle('ring-2', active);
      el.classList.toggle('ring-primary', active);
      el.classList.toggle('border-primary', active);
    });

    if (header) {
      header.classList.remove('hidden');
      header.innerHTML = renderEventHeader(item, timeConfig, championId, domainId);
    }
    if (detail) {
      detail.innerHTML = renderAgentResponses(item.periodData, championId, domainId);
    }
  }

  items.forEach(el => el.addEventListener('click', () => select(el.dataset.eventId)));
  if (selectedId) select(selectedId);
}

function counterfactualCard(cf) {
  return `<div class="glass-panel p-5 bg-white border-l-4 border-l-primary rounded-xl">
    <span class="text-xs font-bold text-primary">T${cf.period}</span>
    <div class="mt-3 grid grid-cols-2 gap-4 text-sm">
      <div><p class="text-[10px] uppercase text-on-surface-variant mb-1">${t('results.actualChoice')}</p><p class="font-medium">${escapeHtml(cf.decision_a)}</p><p class="text-xs text-on-surface-variant mt-1">${escapeHtml(cf.outcome_a)}</p></div>
      <div><p class="text-[10px] uppercase text-on-surface-variant mb-1">${t('results.altChoice')}</p><p class="font-medium">${escapeHtml(cf.decision_b)}</p><p class="text-xs text-on-surface-variant mt-1">${escapeHtml(cf.outcome_b)}</p></div>
    </div>
    <p class="text-xs text-primary font-bold mt-3 pt-3 border-t border-outline-variant">${escapeHtml(cf.difference)}</p>
  </div>`;
}

function roadmapItem(step, n) {
  return `<div class="glass-panel p-4 flex gap-4 items-center bg-white rounded-xl">
    <span class="font-mono text-xl font-bold text-primary w-10">${String(n).padStart(2, '0')}</span>
    <p class="text-sm flex-1">${escapeHtml(step)}</p>
  </div>`;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
