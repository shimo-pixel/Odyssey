import { API, actionLabel, apiOrigin, resolveDomainId } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import { icon } from '../icons.js';
import { getPrefs } from '../prefs.js';
import { renderStatePanel } from '../periodMetrics.js';

const PATH_FETCH_LIMIT = 25;

export function renderResults(simId) {
  return pageShell(`
    <div class="p-6 lg:p-10 max-w-[1400px] mx-auto" id="results-root">
      <div class="flex items-center justify-center py-24">
        <div class="animate-pulse text-primary font-bold">${t('results.loading')}</div>
      </div>
    </div>
  `, { sidebarActive: 'history', simId });
}

export async function mountResults(simId, rootEl = null) {
  const root = rootEl || document.getElementById('results-root') || document.getElementById('sim-workspace');
  if (!root) return;
  try {
    const [result, decisions] = await Promise.all([
      API.getResult(simId),
      API.getDecisions(simId, PATH_FETCH_LIMIT).catch(() => ({ paths: [], event_comparisons: [] })),
    ]);
    const paths = decisions.paths?.length ? decisions.paths : result.agent_paths || [];
    const eventComparisons = decisions.event_comparisons?.length
      ? decisions.event_comparisons
      : result.event_comparisons?.length
        ? result.event_comparisons
        : buildEventComparisonsFromPaths(paths);
    const eventItems = flattenEventItems(eventComparisons);

    const domainId = resolveDomainId(result, decisions);
    root.innerHTML = buildResultsHTML(result, paths, eventComparisons, eventItems, domainId);
    mountInteractions(eventItems, result.champion_agent_id, domainId);
    mountBranchGraph(result.branches || []);
  } catch (e) {
    root.innerHTML = `<div class="glass-panel p-8 text-center"><p class="text-error font-bold">${t('results.loadFailed')}</p>
      <p class="text-sm text-on-surface-variant mt-2">${escapeHtml(e.message)}</p>
      <a href="#simulate" class="inline-block mt-4 text-primary font-bold">${t('sidebar.newRun')}</a></div>`;
  }
}

function eventLabel(eventIndex, eventData) {
  if (eventData?.event_label) return eventData.event_label;
  return t('unit.eventNth', { n: eventIndex });
}

function flattenEventItems(eventComparisons) {
  const items = [];
  for (const evt of eventComparisons) {
    const summaries = evt.event_summaries?.length
      ? evt.event_summaries
      : (evt.events || []).map(type => ({ event_type: type, description: formatEventType(type), impact: 0 }));

    if (!summaries.length) {
      items.push({
        id: `event-${evt.event_index}`,
        event_index: evt.event_index,
        event: { event_type: 'world_update', description: evt.world_summary || eventLabel(evt.event_index, evt), impact: 0 },
        eventData: evt,
      });
      continue;
    }

    summaries.forEach((ev, idx) => {
      items.push({
        id: `event-${evt.event_index}-sub-${idx}`,
        event_index: evt.event_index,
        event: ev,
        eventData: evt,
      });
    });
  }
  return items;
}

function buildEventComparisonsFromPaths(paths) {
  const indices = [...new Set(paths.flatMap(p => (p.steps || []).map(s => s.event_index)))].sort((a, b) => a - b);
  return indices.map(event_index => {
    let ref = null;
    const agents = [];
    for (const path of paths) {
      const step = path.steps?.find(s => s.event_index === event_index);
      if (!step) continue;
      if (!ref) ref = step;
      agents.push({
        agent_id: path.agent_id,
        rank: path.rank,
        label: path.label,
        rationality: path.rationality,
        action: step.action,
        decision: step.decision,
        reasoning: step.reasoning,
        outcome: step.outcome,
        success: step.success,
        action_summary: step.action_summary,
        goal_status: step.goal_status,
      });
    }
    agents.sort((a, b) => a.rank - b.rank);
    return {
      event_index,
      world_summary: ref?.world_summary || '',
      events: ref?.events || [],
      event_summaries: (ref?.events || []).map(type => ({ event_type: type, description: formatEventType(type), impact: 0 })),
      agents,
    };
  });
}

function buildResultsHTML(r, paths, eventComparisons, eventItems, domainId = 'startup') {
  const championId = r.champion_agent_id;
  const totalAgents = eventComparisons.reduce(
      (max, p) => Math.max(max, p.agents?.length || 0),
      0,
    ) || paths.length;

  return `
    <header class="mb-8">
      <h1 class="text-2xl lg:text-[1.75rem] font-semibold text-on-surface tracking-tight">${t('results.title')}</h1>
      <p class="text-sm text-on-surface-variant mt-2 max-w-2xl">
        ${t('results.desc', { n: totalAgents || r.agent_count })}
      </p>
      <div class="flex flex-wrap gap-4 mt-4">
        <statChip label="${t('results.stat.agents')}" value="${r.agent_count}" />
        <statChip label="${t('results.stat.steps')}" value="${r.events_simulated}" />
        <statChip label="${t('results.stat.events')}" value="${eventItems.length}" />
        <statChip label="${t('results.stat.best')}" value="#${paths.find(p => p.agent_id === championId)?.rank || 1}" highlight />
      </div>
      ${totalAgents > 1 ? '' : `
        <p class="text-xs text-tertiary mt-3 bg-tertiary/10 border border-tertiary/20 rounded-lg px-3 py-2 inline-block">
          ${t('results.multiAgentWarn')}
        </p>`}
    </header>

    ${renderResearchSection(r.world_background)}

    <section class="mb-10 grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div class="lg:col-span-4 xl:col-span-3">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-medium flex items-center gap-2">
            ${icon('bolt', 'icon icon--md text-primary')}
            ${t('results.eventList')}
          </h2>
          <span class="text-[10px] font-bold text-on-surface-variant">${t('results.eventCount', { n: eventItems.length })}</span>
        </div>
        <div id="event-list" class="space-y-2 max-h-[620px] overflow-y-auto custom-scrollbar pr-1">
          ${eventItems.length
            ? eventItems.map(item => eventListItem(item, championId, domainId)).join('')
            : `<p class="text-sm text-on-surface-variant p-4">${t('results.noEvents')}</p>`}
        </div>
      </div>
      <div class="lg:col-span-8 xl:col-span-9">
        <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
          ${icon('users', 'icon icon--md text-primary')}
          ${t('results.agentDetail')}
        </h2>
        <div id="event-detail-header" class="glass-panel px-5 py-4 mb-4 rounded-xl hidden"></div>
        <div id="event-detail" class="space-y-3 max-h-[640px] overflow-y-auto custom-scrollbar pr-1">
          <p class="text-sm text-on-surface-variant glass-panel p-6 rounded-xl">${t('results.selectEvent')}</p>
        </div>
      </div>
    </section>

    ${renderBranchSection(r.branches || [])}

    <section class="mb-10">
      <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
        ${icon('route', 'icon icon--md text-primary')}
        ${t('results.counterfactual')}
      </h2>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        ${(r.counterfactuals || []).map(cf => counterfactualCard(cf)).join('') || `<p class="text-on-surface-variant text-sm">${t('results.noCounterfactual')}</p>`}
      </div>
    </section>

    <section class="mb-10">
      <h2 class="text-sm font-medium mb-2 flex items-center gap-2">
        ${icon('map', 'icon icon--md text-primary')}
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
          <span class="text-sm font-medium flex items-center gap-2">
            ${icon('search', 'icon icon--md text-primary')}
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

function formatEventType(type) {
  return String(type || '').replace(/_/g, ' ');
}

function impactLabel(impact) {
  if (impact >= 0.3) return { text: t('common.positive'), cls: 'text-secondary' };
  if (impact <= -0.3) return { text: t('common.negative'), cls: 'text-error' };
  return { text: t('common.neutral'), cls: 'text-on-surface-variant' };
}

function blackSwanChip() {
  return `<span class="black-swan-chip" title="${t('results.blackSwanHint')}">${icon('bolt', 'icon icon--xs')}${t('results.blackSwan')}</span>`;
}

function evidenceList(evidence) {
  const items = (evidence || []).filter(Boolean);
  if (!items.length) return '';
  return `
    <div class="event-evidence">
      <span class="event-evidence-title">${t('results.evidence')}</span>
      <ul>${items.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>
    </div>`;
}

function eventListItem(item, championId, domainId = 'startup') {
  const ev = item.event;
  const impact = impactLabel(ev.impact || 0);
  const agentCount = item.eventData?.agents?.length || 0;
  return `
    <button type="button" data-event-id="${item.id}" data-event-index="${item.event_index}"
      class="event-item w-full text-left p-3.5 rounded-xl border ${ev.is_black_swan ? 'border-tertiary/50 bg-tertiary/5' : 'border-outline-variant bg-white'} hover:border-primary/40 transition-all">
      <div class="flex items-center gap-2 mb-1.5 flex-wrap">
        <span class="font-mono text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded">${eventLabel(item.event_index, item.eventData)}</span>
        <span class="text-[10px] font-bold ${impact.cls}">${impact.text}</span>
        ${ev.is_black_swan ? blackSwanChip() : ''}
      </div>
      <p class="text-sm font-bold text-on-surface leading-snug">${escapeHtml(ev.description || formatEventType(ev.event_type))}</p>
      <p class="text-[10px] text-on-surface-variant font-mono mt-1">${escapeHtml(ev.event_type)}</p>
      <p class="text-[11px] text-on-surface-variant mt-2">${t('results.agentsRespond', { n: agentCount })}</p>
    </button>`;
}

function renderEventHeader(item, championId, domainId = 'startup') {
  const evt = item.eventData;
  const ev = item.event;
  const impact = impactLabel(ev.impact || 0);
  const label = eventLabel(item.event_index, evt);
  return `
    <div>
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <span class="font-mono font-bold text-primary">${escapeHtml(label)}</span>
        <span class="text-xs font-bold ${impact.cls}">${impact.text}</span>
        ${ev.is_black_swan ? blackSwanChip() : ''}
        <span class="text-xs text-on-surface-variant">${t('results.agentsRespond', { n: evt.agents?.length || 0 })}</span>
      </div>
      <h3 class="font-bold text-lg text-on-surface">${escapeHtml(ev.description || formatEventType(ev.event_type))}</h3>
      <p class="text-xs font-mono text-on-surface-variant mt-1">${escapeHtml(ev.event_type)}</p>
    </div>
    <div class="mt-4 text-xs bg-surface-container-low rounded-lg p-3">
      <span class="font-bold text-on-surface block mb-1">${t('results.worldConditions')}</span>
      <p class="text-on-surface-variant leading-relaxed">${escapeHtml(evt.world_summary || t('common.none'))}</p>
      ${(evt.events || []).length > 1 ? `
        <p class="text-on-surface-variant mt-2">${t('results.otherEvents', { events: escapeHtml(evt.events.filter(type => type !== ev.event_type).join(', ') || t('common.none')) })}</p>` : ''}
      ${evidenceList(ev.evidence)}
    </div>`;
}

function renderAgentResponses(eventComparison, championId, domainId = 'startup') {
  const agents = eventComparison.agents || [];
  if (!agents.length) {
    return `<p class="text-sm text-on-surface-variant glass-panel p-6 rounded-xl">${t('results.noAgentData')}</p>`;
  }

  const header = `
    <div class="flex items-center justify-between glass-panel bg-white px-4 py-3 rounded-xl mb-1 sticky top-0 z-10">
      <span class="text-sm font-bold text-on-surface">${t('results.agentCount', { n: agents.length })}</span>
      <span class="text-[10px] text-on-surface-variant">${t('results.agentHint')}</span>
      <span class="text-[10px] text-on-surface-variant hidden sm:inline"> · ${t('results.macroOutcomeHint')}</span>
    </div>`;

  const cards = agents.map(agent => {
    const ok = agent.success !== false;
    const isChampion = agent.agent_id === championId;
    const branchName = agent.label || agent.agent_id;
    const irrational = agent.rationality === 'irrational';
    return `
      <article class="agent-decision-card p-4 rounded-xl border ${isChampion ? 'border-primary bg-primary/5' : 'border-outline-variant bg-white'}">
        <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div class="flex items-center gap-2 flex-wrap">
            ${agent.rank ? `<span class="font-mono text-xs font-bold ${isChampion ? 'text-primary' : 'text-on-surface'}">#${agent.rank}</span>` : ''}
            <span class="text-sm font-semibold text-on-surface">${escapeHtml(branchName)}</span>
            ${isChampion ? `<span class="text-[9px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-full">${t('common.champion')}</span>` : ''}
            ${agent.rationality ? `<span class="rationality-chip rationality-chip--${irrational ? 'irrational' : 'rational'}">${t(irrational ? 'results.irrational' : 'results.rational')}</span>` : ''}
          </div>
          <span class="action-chip ${ok ? 'action-chip-ok' : 'action-chip-fail'}">${actionLabel(agent.action, domainId)}</span>
        </div>
        <div class="space-y-3 text-sm">
          <div class="bg-surface-container-low/80 rounded-lg p-3">
            <span class="text-[10px] font-bold uppercase text-on-surface-variant tracking-wider">${t('results.response')}</span>
            <p class="text-on-surface font-medium mt-1 leading-snug">${escapeHtml(agent.decision || '—')}</p>
            ${agent.reasoning ? `<p class="text-xs text-on-surface-variant mt-2 leading-relaxed">${escapeHtml(agent.reasoning)}</p>` : ''}
          </div>
          <div class="rounded-lg p-3 border border-outline-variant/60 bg-white">
            <span class="text-[10px] font-bold uppercase text-on-surface-variant tracking-wider">${t('results.outcome')}</span>
            <p class="text-sm text-on-surface mt-2 leading-relaxed">${escapeHtml(agent.outcome || (ok ? t('common.success') : t('common.failed')))}</p>
            ${renderStatePanel(agent.metrics, agent.goal_status, { compact: false })}
          </div>
        </div>
      </article>`;
  }).join('');

  return header + cards;
}

function mountInteractions(eventItems, championId, domainId = 'startup') {
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
      header.innerHTML = renderEventHeader(item, championId, domainId);
    }
    if (detail) {
      detail.innerHTML = renderAgentResponses(item.eventData, championId, domainId);
    }
  }

  items.forEach(el => el.addEventListener('click', () => select(el.dataset.eventId)));
  if (selectedId) select(selectedId);
}

function renderBranchSection(branches) {
  if (!branches.length) return '';
  const withGraph = branches.filter(b => (b.workspaces || []).length);
  return `
    <section class="mb-10">
      <h2 class="text-sm font-medium mb-4 flex items-center gap-2">
        ${icon('merge', 'icon icon--md text-primary')}
        ${t('results.branches')}
      </h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        ${branches.map(branchCard).join('')}
      </div>
      ${withGraph.length ? `
        <div class="glass-panel rounded-xl overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-outline-variant">
            <div>
              <h3 class="text-sm font-medium text-on-surface">${t('results.branchGraph')}</h3>
              <p class="text-xs text-on-surface-variant mt-0.5">${t('results.branchGraphHint')}</p>
            </div>
            <select id="branch-graph-select" class="branch-graph-select">
              ${withGraph.map(b => (b.workspaces || []).map(ws => `
                <option value="${escapeHtml(ws)}">${escapeHtml(b.label || b.branch_id)}${b.workspaces.length > 1 ? ` · ${escapeHtml(ws)}` : ''}</option>`).join('')).join('')}
            </select>
          </div>
          <div class="kb-graph-frame-wrap relative">
            <iframe id="branch-graph-frame" title="${t('results.branchGraph')}" class="absolute inset-0 w-full h-full border-0 bg-background" src="about:blank"></iframe>
          </div>
        </div>` : ''}
    </section>`;
}

function branchCard(b) {
  const irrational = b.rationality === 'irrational';
  const progress = Math.max(0, Math.min(100, Number(b.final_progress || 0) * 100));
  const metrics = Object.entries(b.final_metrics || {}).slice(0, 3);
  return `
    <article class="glass-panel bg-white rounded-xl p-4">
      <div class="flex items-center gap-2 flex-wrap mb-2">
        <span class="font-mono text-xs font-bold ${b.rank === 1 ? 'text-primary' : 'text-on-surface'}">#${b.rank || '—'}</span>
        <span class="text-sm font-semibold text-on-surface">${escapeHtml(b.label || b.branch_id)}</span>
        <span class="rationality-chip rationality-chip--${irrational ? 'irrational' : 'rational'}">${t(irrational ? 'results.irrational' : 'results.rational')}</span>
      </div>
      ${b.persona ? `<p class="text-xs text-on-surface-variant leading-relaxed mb-3">${escapeHtml(b.persona)}</p>` : ''}
      <div class="goal-progress-bar" aria-hidden="true">
        <div class="goal-progress-fill" style="width:${progress}%"></div>
      </div>
      <p class="text-xs text-on-surface-variant mt-1.5">${t('results.goalProgress')} <strong class="text-primary">${Math.round(progress)}%</strong></p>
      ${metrics.length ? `<div class="branch-metrics">${metrics.map(([k, v]) =>
        `<span><span class="branch-metric-name">${escapeHtml(k)}</span><strong>${escapeHtml(String(Number(Number(v).toFixed(2))))}</strong></span>`).join('')}</div>` : ''}
    </article>`;
}

async function mountBranchGraph(branches) {
  const select = document.getElementById('branch-graph-select');
  const frame = document.getElementById('branch-graph-frame');
  if (!select || !frame || !branches.length) return;

  const prefs = getPrefs();
  let embedPath = '/lightrag/webui/index.html#/embed/graph';
  try {
    const cfg = await API.getConfig();
    if (cfg.lightrag_embed_path) embedPath = cfg.lightrag_embed_path;
  } catch { /* keep default */ }

  const load = (workspace) => {
    const qs = new URLSearchParams({
      workspace,
      lang: prefs.locale === 'en' ? 'en' : 'zh',
      theme: prefs.theme === 'dark' ? 'dark' : 'light',
      hg: '5',
    });
    frame.src = `${apiOrigin()}${embedPath}?${qs.toString()}`;
  };

  select.addEventListener('change', () => load(select.value));
  if (select.value) load(select.value);
}

function counterfactualCard(cf) {
  return `<div class="glass-panel p-5 bg-white border-l-4 border-l-primary rounded-xl">
    <span class="text-xs font-bold text-primary">${escapeHtml(t('unit.eventNth', { n: cf.event_index }))}</span>
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
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
