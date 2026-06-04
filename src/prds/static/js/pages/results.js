import { API, actionLabel } from '../api.js';
import { pageShell } from '../layout.js';
import { formatPeriodLabel, formatPeriodShort, timeConfigFrom, unitLengthLabel } from '../time.js';

const PATH_FETCH_LIMIT = 25;
const MATRIX_COL_LIMIT = 12;

export function renderResults(simId) {
  return pageShell(`
    <div class="p-6 lg:p-10 max-w-[1400px] mx-auto" id="results-root">
      <div class="flex items-center justify-center py-24">
        <div class="animate-pulse text-primary font-bold">加载决策数据…</div>
      </div>
    </div>
  `, { topNav: 'simulate', sidebarActive: 'results', simId });
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

    root.innerHTML = buildResultsHTML(result, paths, periodComparisons, eventItems, timeConfig);
    mountInteractions(eventItems, periodComparisons, result.champion_agent_id, timeConfig);
  } catch (e) {
    root.innerHTML = `<div class="glass-panel p-8 text-center"><p class="text-error font-bold">无法加载结果</p>
      <p class="text-sm text-on-surface-variant mt-2">${escapeHtml(e.message)}</p>
      <a href="#monitor/${simId}" class="inline-block mt-4 text-primary font-bold">返回监控</a></div>`;
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

function buildResultsHTML(r, paths, periodComparisons, eventItems, timeConfig) {
  const championId = r.champion_agent_id;
  const periods = periodComparisons.length || maxPeriods(paths);
    const totalAgents = periodComparisons.reduce(
      (max, p) => Math.max(max, p.agents?.length || 0),
      0,
    ) || paths.length;

  return `
    <header class="mb-8">
      <span class="text-xs text-primary font-bold uppercase tracking-widest">平行世界决策推演</span>
      <h1 class="text-2xl lg:text-3xl font-bold mt-2 text-on-surface">决策矩阵</h1>
      <p class="text-sm text-on-surface-variant mt-2 max-w-2xl">
        左侧列出推演过程中发生的每个事件；选中后在右侧查看 ${totalAgents || r.agent_count} 个平行智能体各自的应对方式与结果。
      </p>
      <div class="flex flex-wrap gap-4 mt-4">
        <statChip label="平行智能体" value="${r.agent_count}" />
        <statChip label="推演步数" value="${r.periods_simulated}" />
        <statChip label="周期粒度" value="${unitLengthLabel(timeConfig.period_time_unit, timeConfig.period_time_length)}" />
        <statChip label="事件节点" value="${eventItems.length}" />
        <statChip label="最优路径" value="#${paths.find(p => p.agent_id === championId)?.rank || 1}" highlight />
      </div>
      ${totalAgents > 1 ? '' : `
        <p class="text-xs text-tertiary mt-3 bg-tertiary/10 border border-tertiary/20 rounded-lg px-3 py-2 inline-block">
          当前结果缺少多智能体数据。请重新运行推演，或确认服务端已重启至最新版本。
        </p>`}
    </header>

    <section class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">table_chart</span>
          概览矩阵
        </h2>
        <span class="text-xs text-on-surface-variant">行 = 周期 · 列 = 排名前 ${Math.min(paths.length, MATRIX_COL_LIMIT)} 的智能体动作</span>
      </div>
      <div class="glass-panel bg-white overflow-x-auto rounded-xl">
        ${buildDecisionMatrix(paths, periods, championId, periodComparisons, timeConfig)}
      </div>
    </section>

    <section class="mb-10 grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div class="lg:col-span-4 xl:col-span-3">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-bold flex items-center gap-2">
            <span class="material-symbols-outlined text-tertiary">bolt</span>
            事件列表
          </h2>
          <span class="text-[10px] font-bold text-on-surface-variant">${eventItems.length} 个</span>
        </div>
        <div id="event-list" class="space-y-2 max-h-[620px] overflow-y-auto custom-scrollbar pr-1">
          ${eventItems.length
            ? eventItems.map(item => eventListItem(item, timeConfig)).join('')
            : '<p class="text-sm text-on-surface-variant p-4">暂无事件数据</p>'}
        </div>
      </div>
      <div class="lg:col-span-8 xl:col-span-9">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">groups</span>
          智能体应对详情
        </h2>
        <div id="event-detail-header" class="glass-panel bg-white px-5 py-4 mb-4 rounded-xl hidden"></div>
        <div id="event-detail" class="space-y-3 max-h-[640px] overflow-y-auto custom-scrollbar pr-1">
          <p class="text-sm text-on-surface-variant glass-panel bg-white p-6 rounded-xl">← 从左侧选择一个事件，查看各智能体的应对与后果</p>
        </div>
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
        <span class="material-symbols-outlined text-tertiary">alt_route</span>
        关键节点反事实
      </h2>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        ${(r.counterfactuals || []).map(cf => counterfactualCard(cf)).join('') || '<p class="text-on-surface-variant text-sm">暂无</p>'}
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-lg font-bold mb-2 flex items-center gap-2">
        <span class="material-symbols-outlined text-primary">map</span>
        收敛路线图
      </h2>
      <p class="text-xs text-on-surface-variant mb-4">${escapeHtml(r.synthesis?.disclaimer || '')}</p>
      <div class="space-y-2">
        ${(r.synthesis?.recommended_roadmap || []).map((step, i) => roadmapItem(step, i + 1)).join('')}
      </div>
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
  if (impact >= 0.3) return { text: '有利', cls: 'text-secondary' };
  if (impact <= -0.3) return { text: '不利', cls: 'text-error' };
  return { text: '中性', cls: 'text-on-surface-variant' };
}

function eventListItem(item, timeConfig) {
  const ev = item.event;
  const impact = impactLabel(ev.impact || 0);
  const agentCount = item.periodData?.agents?.length || 0;
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
      <p class="text-[11px] text-on-surface-variant mt-2">${agentCount} 个智能体应对</p>
    </button>`;
}

function renderEventHeader(item, timeConfig) {
  const period = item.periodData;
  const ev = item.event;
  const impact = impactLabel(ev.impact || 0);
  const label = periodLabel(item.period, timeConfig, period);
  return `
    <div>
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <span class="font-mono font-bold text-primary">${label}</span>
        <span class="text-xs font-bold ${impact.cls}">${impact.text}</span>
        <span class="text-xs text-on-surface-variant">${period.agents?.length || 0} 个智能体</span>
      </div>
      <h3 class="font-bold text-lg text-on-surface">${escapeHtml(ev.description || formatEventType(ev.event_type))}</h3>
      <p class="text-xs font-mono text-on-surface-variant mt-1">${escapeHtml(ev.event_type)}</p>
    </div>
    <div class="mt-4 text-xs bg-surface-container-low rounded-lg p-3">
      <span class="font-bold text-on-surface block mb-1">世界条件</span>
      <p class="text-on-surface-variant leading-relaxed">${escapeHtml(period.world_summary || '—')}</p>
      ${(period.events || []).length > 1 ? `
        <p class="text-on-surface-variant mt-2">同周期其他事件：${escapeHtml(period.events.filter(t => t !== ev.event_type).join('、') || '—')}</p>` : ''}
    </div>`;
}

function renderAgentResponses(period, championId) {
  const agents = period.agents || [];
  if (!agents.length) {
    return '<p class="text-sm text-on-surface-variant glass-panel bg-white p-6 rounded-xl">该事件暂无智能体应对数据</p>';
  }

  const header = `
    <div class="flex items-center justify-between glass-panel bg-white px-4 py-3 rounded-xl mb-1 sticky top-0 z-10">
      <span class="text-sm font-bold text-on-surface">共 ${agents.length} 个智能体应对</span>
      <span class="text-[10px] text-on-surface-variant">各路径在相同事件下的不同选择与后果</span>
    </div>`;

  const cards = agents.map(agent => {
    const ok = agent.success !== false;
    const isChampion = agent.agent_id === championId;
    return `
      <article class="agent-decision-card p-4 rounded-xl border ${isChampion ? 'border-primary bg-primary/5' : 'border-outline-variant bg-white'}">
        <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div class="flex items-center gap-2 flex-wrap">
            ${agent.rank ? `<span class="font-mono text-xs font-bold ${isChampion ? 'text-primary' : 'text-on-surface'}">#${agent.rank}</span>` : ''}
            ${isChampion ? '<span class="text-[9px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-full">最优</span>' : ''}
            <span class="text-[10px] font-mono text-on-surface-variant">${agent.agent_id.slice(0, 16)}…</span>
          </div>
          <span class="action-chip ${ok ? 'action-chip-ok' : 'action-chip-fail'}">${actionLabel(agent.action)}</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div class="bg-surface-container-low/80 rounded-lg p-3">
            <span class="text-[10px] font-bold uppercase text-on-surface-variant tracking-wider">应对方式</span>
            <p class="text-on-surface font-medium mt-1 leading-snug">${escapeHtml(agent.decision || '—')}</p>
            ${agent.reasoning ? `<p class="text-xs text-on-surface-variant mt-2 leading-relaxed">${escapeHtml(agent.reasoning)}</p>` : ''}
          </div>
          <div class="rounded-lg p-3 ${ok ? 'bg-secondary/5 border border-secondary/15' : 'bg-error/5 border border-error/15'}">
            <span class="text-[10px] font-bold uppercase ${ok ? 'text-secondary' : 'text-error'} tracking-wider">结果</span>
            <p class="text-xs ${ok ? 'text-secondary' : 'text-error'} mt-1 leading-relaxed font-medium">${escapeHtml(agent.outcome || (ok ? '执行完成' : '执行失败'))}</p>
          </div>
        </div>
      </article>`;
  }).join('');

  return header + cards;
}

function buildDecisionMatrix(paths, periods, championId, periodComparisons, timeConfig) {
  const periodCount = typeof periods === 'number'
    ? periods
    : Math.max(periodComparisons.length, maxPeriods(paths));

  if (!paths.length && !periodComparisons.length) {
    return '<p class="p-6 text-sm text-on-surface-variant">暂无决策数据，请重新运行推演。</p>';
  }

  const cols = paths.slice(0, MATRIX_COL_LIMIT);
  const header = `
    <thead><tr class="border-b border-outline-variant bg-surface-container-low">
      <th class="decision-matrix-cell sticky left-0 bg-surface-container-low z-10 text-left font-bold text-xs uppercase text-on-surface-variant">时间节点</th>
      <th class="decision-matrix-cell text-left text-xs uppercase text-on-surface-variant min-w-[180px]">事件</th>
      ${cols.map(p => `
        <th class="decision-matrix-cell text-center text-xs min-w-[100px] ${p.agent_id === championId ? 'bg-primary/5' : ''}">
          <span class="font-bold ${p.agent_id === championId ? 'text-primary' : ''}">#${p.rank}</span>
          ${p.agent_id === championId ? '<span class="block text-[9px] text-primary">最优</span>' : ''}
        </th>`).join('')}
    </tr></thead>`;

  let rows = '';
  for (let t = 1; t <= periodCount; t++) {
    const periodData = periodComparisons.find(p => p.period === t);
    const refStep = cols[0]?.steps?.find(s => s.period === t);
    const events = periodData?.events?.slice(0, 2).join(', ') || refStep?.events?.slice(0, 2).join(', ') || '—';
    const world = periodData?.world_summary?.slice(0, 60) || refStep?.world_summary?.slice(0, 60) || '—';

    rows += `<tr class="border-b border-outline-variant/50 hover:bg-surface-container-low/50">
      <td class="decision-matrix-cell sticky left-0 bg-white z-10">
        <span class="font-mono text-xs font-bold text-primary block">${formatPeriodShort(t, timeConfig).split(' · ')[0]}</span>
        <span class="font-mono text-[10px] text-on-surface-variant">T${t}</span>
      </td>
      <td class="decision-matrix-cell text-xs text-on-surface-variant">
        <p class="font-medium text-on-surface mb-0.5">${escapeHtml(world)}</p>
        ${events !== '—' ? `<span class="text-[10px] text-tertiary">${escapeHtml(events)}</span>` : ''}
      </td>
      ${cols.map(p => {
        const step = p.steps?.find(s => s.period === t);
        if (!step) return '<td class="decision-matrix-cell text-center text-outline text-xs">—</td>';
        const ok = step.success !== false;
        return `<td class="decision-matrix-cell text-center ${p.agent_id === championId ? 'bg-primary/[0.03]' : ''}">
          <span class="action-chip ${ok ? 'action-chip-ok' : 'action-chip-fail'}">${actionLabel(step.action)}</span>
        </td>`;
      }).join('')}
    </tr>`;
  }

  return `<table class="decision-matrix w-full text-sm">${header}<tbody>${rows}</tbody></table>`;
}

function mountInteractions(eventItems, periodComparisons, championId, timeConfig) {
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
      header.innerHTML = renderEventHeader(item, timeConfig);
    }
    if (detail) {
      detail.innerHTML = renderAgentResponses(item.periodData, championId);
    }
  }

  items.forEach(el => el.addEventListener('click', () => select(el.dataset.eventId)));
  if (selectedId) select(selectedId);
}

function counterfactualCard(cf) {
  return `<div class="glass-panel p-5 bg-white border-l-4 border-l-primary rounded-xl">
    <span class="text-xs font-bold text-primary">T${cf.period}</span>
    <div class="mt-3 grid grid-cols-2 gap-4 text-sm">
      <div><p class="text-[10px] uppercase text-on-surface-variant mb-1">实际选择</p><p class="font-medium">${escapeHtml(cf.decision_a)}</p><p class="text-xs text-on-surface-variant mt-1">${escapeHtml(cf.outcome_a)}</p></div>
      <div><p class="text-[10px] uppercase text-on-surface-variant mb-1">备选选择</p><p class="font-medium">${escapeHtml(cf.decision_b)}</p><p class="text-xs text-on-surface-variant mt-1">${escapeHtml(cf.outcome_b)}</p></div>
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
