import { API } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';

const D3_URL = 'https://cdn.jsdelivr.net/npm/d3@7/+esm';
let _d3 = null;
async function loadD3() {
  if (_d3) return _d3;
  _d3 = await import(D3_URL);
  return _d3;
}

// Known entity-type styling; unknown types (e.g. arbitrary Graphiti labels) get
// a color from the fallback palette.
const KNOWN_TYPES = {
  person: { color: '#1a73e8', icon: 'person' },
  organization: { color: '#1e8e3e', icon: 'corporate_fare' },
  product: { color: '#e8710a', icon: 'inventory_2' },
  capital: { color: '#9334e6', icon: 'payments' },
  market: { color: '#d93025', icon: 'storefront' },
  technology: { color: '#f9ab00', icon: 'memory' },
  time: { color: '#5f6368', icon: 'schedule' },
  event: { color: '#e52592', icon: 'bolt' },
  agent: { color: '#00897b', icon: 'smart_toy' },
  entity: { color: '#1a73e8', icon: 'category' },
  risk: { color: '#d93025', icon: 'warning' },
};
const PALETTE = ['#1a73e8', '#1e8e3e', '#e8710a', '#9334e6', '#d93025', '#f9ab00', '#00897b', '#e52592', '#3949ab', '#00838f'];

let pollTimer = null;
let currentSim = null;

export function renderKnowledge(simId) {
  return pageShell(`
    <div class="mr-0 lg:mr-80 h-screen relative bg-background overflow-hidden">
      <div class="absolute top-4 left-4 glass-panel p-4 rounded-lg z-20 max-w-xs">
        <h4 class="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">${t('kg.worldBg')}</h4>
        <p id="kg-bg-summary" class="text-xs text-on-surface-variant leading-relaxed line-clamp-4">${t('common.loading')}</p>
        <p id="kg-source" class="text-[10px] text-primary font-bold mt-2"></p>
      </div>

      <div class="absolute top-4 right-4 flex items-center gap-2 z-20">
        <div class="glass-panel px-3 py-2 rounded-lg flex items-center gap-2">
          <label class="flex items-center gap-2 cursor-pointer text-xs text-on-surface">
            <input id="kg-edgelabels" type="checkbox" checked class="accent-primary"/>
            ${t('kg.edgeLabels')}
          </label>
        </div>
        <button id="kg-refresh" class="glass-panel px-3 py-2 rounded-lg flex items-center gap-1.5 text-xs font-bold text-primary hover:bg-surface-container-high transition-colors">
          <span id="kg-refresh-icon" class="material-symbols-outlined text-base">refresh</span>
          ${t('kg.refresh')}
        </button>
      </div>

      <div id="kg-building" class="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 hidden">
        <div class="glass-panel px-4 py-2 rounded-full flex items-center gap-2 text-xs text-on-surface">
          <span class="material-symbols-outlined text-base text-secondary animate-pulse">hub</span>
          ${t('kg.live')}
        </div>
      </div>

      <div id="graph-viewport" class="w-full h-full">
        <svg id="kg-svg" class="w-full h-full"></svg>
      </div>

      <div id="kg-legend" class="absolute bottom-4 left-4 glass-panel p-3 rounded-lg z-20 hidden lg:block">
        <h4 class="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">${t('kg.entityTypes')}</h4>
        <div id="kg-legend-items" class="flex flex-col gap-1.5 text-xs max-h-48 overflow-y-auto custom-scrollbar"></div>
      </div>

      <aside id="kg-sidebar" class="fixed right-0 top-0 h-screen w-80 bg-surface border-l border-outline-variant p-6 z-30 translate-x-full transition-transform overflow-y-auto custom-scrollbar">
        <div class="flex justify-between items-center mb-6">
          <h3 id="kg-detail-title" class="font-bold">${t('kg.nodeDetail')}</h3>
          <button id="kg-close" class="material-symbols-outlined text-on-surface-variant hover:text-on-surface">close</button>
        </div>
        <div id="kg-detail"><p class="text-sm text-on-surface-variant">${t('kg.clickNode')}</p></div>
      </aside>

      <div id="kg-empty" class="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div class="glass-panel p-8 text-center max-w-md pointer-events-auto">
          <p class="text-on-surface-variant mb-4" id="kg-msg">${t('kg.empty')}</p>
          <a href="#simulate" class="text-primary font-bold">${t('kg.startSim')}</a>
        </div>
      </div>
    </div>
  `, { sidebarActive: 'knowledge', simId, mainClass: 'ml-60 min-h-screen bg-background' });
}

export async function mountKnowledge(simId) {
  const id = simId || localStorage.getItem('prds_last_sim');
  currentSim = id;
  stopPolling();

  document.getElementById('kg-close')?.addEventListener('click', () => {
    document.getElementById('kg-sidebar')?.classList.add('translate-x-full');
  });
  document.getElementById('kg-refresh')?.addEventListener('click', () => loadAndRender(id, { manual: true }));
  document.getElementById('kg-edgelabels')?.addEventListener('change', (e) => {
    toggleEdgeLabels(e.target.checked);
  });

  if (!id) return;

  try {
    const status = await API.getStatus(id);
    await loadAndRender(id, { status: status.status });
    if (status.status !== 'completed') {
      startPolling(id);
    }
  } catch (e) {
    const msg = document.getElementById('kg-msg');
    if (msg) msg.textContent = t('kg.loadFailed', { msg: e.message });
  }
}

function startPolling(id) {
  stopPolling();
  pollTimer = setInterval(async () => {
    // Stop if the user navigated away (DOM swapped by the router).
    if (!document.getElementById('kg-svg') || currentSim !== id) {
      stopPolling();
      return;
    }
    try {
      const status = await API.getStatus(id);
      await loadAndRender(id, { status: status.status, silent: true });
      if (status.status === 'completed') stopPolling();
    } catch (_) { /* keep polling */ }
  }, 4000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function loadAndRender(id, { manual = false, silent = false, status = null } = {}) {
  const icon = document.getElementById('kg-refresh-icon');
  if (manual && icon) icon.classList.add('animate-spin');
  try {
    const data = await API.getKnowledgeGraph(id);
    const kg = data.knowledge_graph || {};
    if (!kg.nodes || !kg.nodes.length) {
      if (!silent) {
        const msg = document.getElementById('kg-msg');
        if (msg) msg.textContent = status && status !== 'completed' ? t('kg.building') : t('kg.empty');
      }
      return;
    }
    document.getElementById('kg-empty')?.classList.add('hidden');

    const bg = data.world_background || {};
    const sumEl = document.getElementById('kg-bg-summary');
    if (sumEl) sumEl.textContent = bg.summary || t('kg.noSummary');
    const srcEl = document.getElementById('kg-source');
    if (srcEl) {
      const src = sourceLabel(data.graph_source || bg.graph_source);
      const neo = bg.neo4j_persisted ? ' · Neo4j' : '';
      srcEl.textContent = `${src}${neo}`;
    }

    const building = document.getElementById('kg-building');
    if (building) building.classList.toggle('hidden', !(data.building || (status && status !== 'completed')));

    await renderGraph(kg);
  } catch (e) {
    if (!silent) {
      const msg = document.getElementById('kg-msg');
      if (msg) msg.textContent = t('kg.loadFailed', { msg: e.message });
    }
  } finally {
    if (manual && icon) setTimeout(() => icon.classList.remove('animate-spin'), 400);
  }
}

function sourceLabel(source) {
  if (source === 'graphiti') return t('kg.source.graphiti');
  if (source === 'graphrag') return t('kg.source.graphrag');
  return t('kg.source.ontology');
}

function pickType(n) {
  if (n.entity_type) return n.entity_type;
  if (Array.isArray(n.labels)) {
    const l = n.labels.find((x) => x && x !== 'Entity');
    if (l) return l;
  }
  return n.type || 'entity';
}

function normalizeGraph(kg) {
  const rawNodes = kg.nodes || [];
  const rawEdges = kg.edges || [];
  const nodes = rawNodes
    .map((n) => ({
      id: n.uuid || n.id,
      name: n.name || n.label || n.uuid || n.id || '',
      type: pickType(n),
      summary: n.summary || n.description || n.properties?.description || '',
      raw: n,
    }))
    .filter((n) => n.id);
  const ids = new Set(nodes.map((n) => n.id));
  const edges = rawEdges
    .map((e) => ({
      source: e.source ?? e.source_node_uuid,
      target: e.target ?? e.target_node_uuid,
      label: e.relation_type || e.name || e.fact_type || 'related',
      fact: e.fact || '',
      raw: e,
    }))
    .filter((e) => ids.has(e.source) && ids.has(e.target));
  return { nodes, edges };
}

function buildColorMap(types) {
  const map = {};
  let pi = 0;
  for (const ty of types) {
    if (KNOWN_TYPES[ty]) {
      map[ty] = KNOWN_TYPES[ty].color;
    } else {
      map[ty] = PALETTE[pi % PALETTE.length];
      pi += 1;
    }
  }
  return map;
}

// Persisted view state across re-renders (zoom transform + node positions).
let _viewState = { transform: null, positions: new Map(), simId: null };
let _sim = null;
let _showEdgeLabels = true;
let _edgeLabelSel = null;
let _edgeLabelBgSel = null;

function toggleEdgeLabels(show) {
  _showEdgeLabels = show;
  const disp = show ? null : 'none';
  if (_edgeLabelSel) _edgeLabelSel.style('display', disp);
  if (_edgeLabelBgSel) _edgeLabelBgSel.style('display', disp);
}

async function renderGraph(kg) {
  let d3;
  try {
    d3 = await loadD3();
  } catch (_) {
    renderFallback(kg);
    return;
  }

  const svgEl = document.getElementById('kg-svg');
  const viewport = document.getElementById('graph-viewport');
  if (!svgEl || !viewport) return;

  const { nodes, edges } = normalizeGraph(kg);
  if (!nodes.length) return;

  if (_viewState.simId !== currentSim) {
    _viewState = { transform: null, positions: new Map(), simId: currentSim };
  }

  const width = viewport.clientWidth || 1200;
  const height = viewport.clientHeight || 800;

  // Restore prior positions so polling re-renders don't jolt the layout.
  for (const n of nodes) {
    const p = _viewState.positions.get(n.id);
    if (p) {
      n.x = p.x;
      n.y = p.y;
    }
  }

  const types = [...new Set(nodes.map((n) => n.type))];
  const colorMap = buildColorMap(types);
  const getColor = (ty) => colorMap[ty] || '#9aa0a6';
  renderLegend(types, colorMap);

  if (_sim) _sim.stop();

  const svg = d3.select(svgEl).attr('viewBox', `0 0 ${width} ${height}`);
  svg.selectAll('*').remove();

  const root = svg.append('g');

  const zoom = d3.zoom().scaleExtent([0.1, 4]).on('zoom', (event) => {
    root.attr('transform', event.transform);
    _viewState.transform = event.transform;
  });
  svg.call(zoom);
  if (_viewState.transform) {
    svg.call(zoom.transform, _viewState.transform);
  }

  // Count parallel edges per node-pair to spread them with curvature.
  const pairCount = {};
  edges.forEach((e) => {
    const key = [e.source, e.target].sort().join('|');
    pairCount[key] = (pairCount[key] || 0) + 1;
  });
  const pairIdx = {};
  edges.forEach((e) => {
    const key = [e.source, e.target].sort().join('|');
    const total = pairCount[key];
    const idx = pairIdx[key] || 0;
    pairIdx[key] = idx + 1;
    e._total = total;
    e._idx = idx;
    e._curv = total > 1 ? (idx / (total - 1) - 0.5) * 1.4 : 0;
  });

  const sim = d3
    .forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id((d) => d.id).distance(110))
    .force('charge', d3.forceManyBody().strength(-340))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(34))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05));
  _sim = sim;

  const linkG = root.append('g').attr('class', 'kg-links');
  const link = linkG
    .selectAll('path')
    .data(edges)
    .enter()
    .append('path')
    .attr('fill', 'none')
    .attr('stroke', 'var(--md-outline-variant)')
    .attr('stroke-width', 1.4)
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation();
      showEdgeDetail(d);
    });

  const edgeLabelBg = linkG
    .selectAll('rect')
    .data(edges)
    .enter()
    .append('rect')
    .attr('fill', 'var(--md-surface)')
    .attr('opacity', 0.85)
    .attr('rx', 3)
    .style('display', _showEdgeLabels ? null : 'none');

  const edgeLabel = linkG
    .selectAll('text')
    .data(edges)
    .enter()
    .append('text')
    .text((d) => d.label)
    .attr('font-size', '9px')
    .attr('fill', 'var(--md-on-surface-variant)')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('pointer-events', 'none')
    .style('display', _showEdgeLabels ? null : 'none');
  _edgeLabelSel = edgeLabel;
  _edgeLabelBgSel = edgeLabelBg;

  const nodeG = root.append('g').attr('class', 'kg-nodes');
  const node = nodeG
    .selectAll('g')
    .data(nodes)
    .enter()
    .append('g')
    .style('cursor', 'pointer')
    .call(
      d3
        .drag()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }),
    )
    .on('click', (event, d) => {
      event.stopPropagation();
      node.select('circle').attr('stroke', 'var(--md-surface)').attr('stroke-width', 2);
      d3.select(event.currentTarget).select('circle').attr('stroke', '#E91E63').attr('stroke-width', 3.5);
      showNodeDetail(d, getColor(d.type));
    });

  node
    .append('circle')
    .attr('r', 11)
    .attr('fill', (d) => getColor(d.type))
    .attr('stroke', 'var(--md-surface)')
    .attr('stroke-width', 2);

  node
    .append('text')
    .text((d) => (d.name.length > 9 ? `${d.name.slice(0, 9)}…` : d.name))
    .attr('font-size', '10px')
    .attr('fill', 'var(--md-on-surface)')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none');

  svg.on('click', () => {
    document.getElementById('kg-sidebar')?.classList.add('translate-x-full');
    node.select('circle').attr('stroke', 'var(--md-surface)').attr('stroke-width', 2);
  });

  const linkPath = (d) => {
    const sx = d.source.x;
    const sy = d.source.y;
    const tx = d.target.x;
    const ty = d.target.y;
    if (!d._curv) return `M${sx},${sy} L${tx},${ty}`;
    const dx = tx - sx;
    const dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const off = Math.max(30, dist * 0.25) * d._curv;
    const cx = (sx + tx) / 2 - (dy / dist) * off;
    const cy = (sy + ty) / 2 + (dx / dist) * off;
    return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`;
  };
  const midPoint = (d) => {
    const sx = d.source.x;
    const sy = d.source.y;
    const tx = d.target.x;
    const ty = d.target.y;
    if (!d._curv) return { x: (sx + tx) / 2, y: (sy + ty) / 2 };
    const dx = tx - sx;
    const dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const off = Math.max(30, dist * 0.25) * d._curv;
    const cx = (sx + tx) / 2 - (dy / dist) * off;
    const cy = (sy + ty) / 2 + (dx / dist) * off;
    return { x: 0.25 * sx + 0.5 * cx + 0.25 * tx, y: 0.25 * sy + 0.5 * cy + 0.25 * ty };
  };

  sim.on('tick', () => {
    link.attr('d', linkPath);
    edgeLabel.each(function (d) {
      const m = midPoint(d);
      d3.select(this).attr('x', m.x).attr('y', m.y);
    });
    edgeLabelBg.each(function (d, i) {
      const m = midPoint(d);
      const textEl = edgeLabel.nodes()[i];
      const bb = textEl.getBBox();
      d3.select(this)
        .attr('x', m.x - bb.width / 2 - 3)
        .attr('y', m.y - bb.height / 2 - 1)
        .attr('width', bb.width + 6)
        .attr('height', bb.height + 2);
    });
    node.attr('transform', (d) => `translate(${d.x},${d.y})`);
  });

  sim.on('end', () => {
    _viewState.positions = new Map(nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
  });
  // Also snapshot positions periodically during ticks for polling continuity.
  sim.on('tick.persist', () => {
    _viewState.positions = new Map(nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
  });
}

function renderLegend(types, colorMap) {
  const box = document.getElementById('kg-legend');
  const items = document.getElementById('kg-legend-items');
  if (!box || !items) return;
  box.classList.remove('hidden');
  items.innerHTML = types
    .map(
      (ty) =>
        `<div class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${colorMap[ty]}"></span><span class="text-on-surface-variant truncate">${escapeText(ty)}</span></div>`,
    )
    .join('');
}

function showNodeDetail(d, color) {
  const sidebar = document.getElementById('kg-sidebar');
  const detail = document.getElementById('kg-detail');
  const title = document.getElementById('kg-detail-title');
  if (!sidebar || !detail) return;
  if (title) title.textContent = t('kg.nodeDetail');
  sidebar.classList.remove('translate-x-full');
  const icon = KNOWN_TYPES[d.type]?.icon || 'category';
  const attrs = d.raw.attributes || {};
  const attrRows = Object.entries(attrs)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .slice(0, 12)
    .map(
      ([k, v]) =>
        `<div class="flex justify-between gap-3 text-xs py-1 border-b border-outline-variant/30"><span class="text-on-surface-variant">${escapeText(k)}</span><span class="font-mono text-on-surface text-right">${escapeText(String(v))}</span></div>`,
    )
    .join('');
  detail.innerHTML = `
    <div class="w-12 h-12 rounded-lg flex items-center justify-center mb-4" style="background:${color}22">
      <span class="material-symbols-outlined" style="color:${color}">${icon}</span>
    </div>
    <h4 class="font-bold text-lg break-words">${escapeText(d.name)}</h4>
    <p class="text-xs font-mono text-outline mt-1">${escapeText(d.type)}</p>
    ${d.summary ? `<p class="text-sm text-on-surface-variant mt-4 leading-relaxed">${escapeText(d.summary)}</p>` : ''}
    ${attrRows ? `<div class="mt-4"><p class="text-[11px] font-bold uppercase text-on-surface-variant tracking-wider mb-1">${t('kg.properties')}</p>${attrRows}</div>` : ''}`;
}

function showEdgeDetail(d) {
  const sidebar = document.getElementById('kg-sidebar');
  const detail = document.getElementById('kg-detail');
  const title = document.getElementById('kg-detail-title');
  if (!sidebar || !detail) return;
  if (title) title.textContent = t('kg.edgeDetail');
  sidebar.classList.remove('translate-x-full');
  const sName = d.source.name || d.source.id;
  const tName = d.target.name || d.target.id;
  detail.innerHTML = `
    <div class="rounded-lg bg-surface-container-low p-3 text-sm font-medium text-on-surface mb-4 leading-relaxed break-words">
      ${escapeText(sName)} <span class="text-primary">→ ${escapeText(d.label)} →</span> ${escapeText(tName)}
    </div>
    ${d.fact ? `<div><p class="text-[11px] font-bold uppercase text-on-surface-variant tracking-wider mb-1">${t('kg.fact')}</p><p class="text-sm text-on-surface-variant leading-relaxed">${escapeText(d.fact)}</p></div>` : ''}`;
}

// Minimal static fallback if the D3 CDN can't be reached.
function renderFallback(kg) {
  const svg = document.getElementById('kg-svg');
  if (!svg) return;
  const { nodes, edges } = normalizeGraph(kg);
  if (!nodes.length) return;
  const W = 1200;
  const H = 800;
  const cx = W / 2;
  const cy = H / 2;
  const r = Math.min(W, H) * 0.36;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const types = [...new Set(nodes.map((n) => n.type))];
  const colorMap = buildColorMap(types);
  renderLegend(types, colorMap);
  const pos = new Map();
  nodes.slice(0, 80).forEach((n, i) => {
    const a = (i / Math.min(nodes.length, 80)) * Math.PI * 2 - Math.PI / 2;
    pos.set(n.id, { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r });
  });
  let html = '';
  edges.forEach((e) => {
    const a = pos.get(e.source);
    const b = pos.get(e.target);
    if (a && b) html += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#c7c4d7" stroke-width="1"/>`;
  });
  nodes.slice(0, 80).forEach((n) => {
    const p = pos.get(n.id);
    const c = colorMap[n.type] || '#9aa0a6';
    html += `<g transform="translate(${p.x},${p.y})"><circle r="10" fill="${c}33" stroke="${c}" stroke-width="2"/><text text-anchor="middle" dy="4" font-size="10" fill="${c}">${escapeText((n.name || n.id).slice(0, 6))}</text></g>`;
  });
  svg.innerHTML = html;
}

function escapeText(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
