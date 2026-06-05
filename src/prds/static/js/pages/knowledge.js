import { API } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';

function typeColors() {
  return {
    person: { stroke: '#1a73e8', icon: 'person', label: t('kg.type.person') },
    organization: { stroke: '#1e8e3e', icon: 'corporate_fare', label: t('kg.type.organization') },
    product: { stroke: '#e8710a', icon: 'inventory_2', label: t('kg.type.product') },
    capital: { stroke: '#9334e6', icon: 'payments', label: t('kg.type.capital') },
    market: { stroke: '#d93025', icon: 'storefront', label: t('kg.type.market') },
    technology: { stroke: '#f9ab00', icon: 'memory', label: t('kg.type.technology') },
    time: { stroke: '#5f6368', icon: 'schedule', label: t('kg.type.time') },
    entity: { stroke: '#1a73e8', icon: 'category', label: t('kg.type.entity') },
    risk: { stroke: '#d93025', icon: 'warning', label: t('kg.type.risk') },
  };
}

export function renderKnowledge(simId) {
  const TYPE_COLORS = typeColors();
  return pageShell(`
    <div class="mr-0 lg:mr-80 h-screen relative bg-background overflow-hidden">
      <div class="absolute top-4 left-4 glass-panel p-4 rounded-lg z-20 max-w-xs">
        <h4 class="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">${t('kg.worldBg')}</h4>
        <p id="kg-bg-summary" class="text-xs text-on-surface-variant leading-relaxed line-clamp-4">${t('common.loading')}</p>
        <p id="kg-source" class="text-[10px] text-primary font-bold mt-2"></p>
      </div>
      <div class="absolute top-4 left-[280px] glass-panel p-4 rounded-lg z-20 hidden lg:block">
        <h4 class="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">${t('kg.entityTypes')}</h4>
        <div class="flex flex-col gap-2 text-xs">
          ${Object.entries(TYPE_COLORS).slice(0, 4).map(([, v]) => `<div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${v.stroke}"></span>${v.label}</div>`).join('')}
        </div>
      </div>
      <div id="graph-viewport" class="w-full h-full">
        <svg id="kg-svg" class="w-full h-full" viewBox="0 0 1200 800"></svg>
      </div>
      <aside id="kg-sidebar" class="fixed right-0 top-0 h-screen w-80 bg-surface border-l border-outline-variant p-6 z-30 translate-x-full transition-transform overflow-y-auto custom-scrollbar">
        <div class="flex justify-between items-center mb-6">
          <h3 class="font-bold">${t('kg.nodeDetail')}</h3>
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
  document.getElementById('kg-close')?.addEventListener('click', () => {
    document.getElementById('kg-sidebar')?.classList.add('translate-x-full');
  });
  if (!id) return;
  try {
    const status = await API.getStatus(id);
    if (status.status !== 'completed') {
      document.getElementById('kg-msg').textContent = t('kg.building');
      const link = document.querySelector('#kg-empty a');
      if (link) {
        link.href = `#monitor/${id}`;
        link.textContent = t('kg.viewProgress');
      }
      return;
    }
    const data = await API.getKnowledgeGraph(id);
    document.getElementById('kg-empty')?.classList.add('hidden');
    const bg = data.world_background || {};
    document.getElementById('kg-bg-summary').textContent = bg.summary || t('kg.noSummary');
    const source = bg.graph_source === 'graphrag' ? t('kg.source.graphrag') : t('kg.source.ontology');
    const neo = bg.neo4j_persisted ? ' · Neo4j' : '';
    document.getElementById('kg-source').textContent = `${source}${neo}`;
    renderGraph(data.knowledge_graph, data.ontology, bg);
  } catch (e) {
    document.getElementById('kg-msg').textContent = t('kg.loadFailed', { msg: e.message });
  }
}

function renderGraph(kg, ontology, worldBackground) {
  const svg = document.getElementById('kg-svg');
  if (!svg || !kg?.nodes?.length) return;

  const TYPE_COLORS = typeColors();
  const width = 1200;
  const height = 800;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  const nodes = kg.nodes.slice(0, 24);
  const edges = kg.edges?.slice(0, 40) || [];

  let svgContent = '';
  edges.forEach(edge => {
    const si = nodes.findIndex(n => n.id === edge.source);
    const ti = nodes.findIndex(n => n.id === edge.target);
    if (si < 0 || ti < 0) return;
    const a = (si / nodes.length) * Math.PI * 2 - Math.PI / 2;
    const b = (ti / nodes.length) * Math.PI * 2 - Math.PI / 2;
    const x1 = cx + Math.cos(a) * radius;
    const y1 = cy + Math.sin(a) * radius;
    const x2 = cx + Math.cos(b) * radius;
    const y2 = cy + Math.sin(b) * radius;
    svgContent += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#c7c4d7" stroke-width="1" class="edge-line"/>`;
  });

  nodes.forEach((node, i) => {
    const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    const tc = TYPE_COLORS[node.type] || TYPE_COLORS.entity;
    svgContent += `
      <g class="graph-node" data-id="${node.id}" transform="translate(${x},${y})">
        <circle r="22" fill="${tc.stroke}15" stroke="${tc.stroke}" stroke-width="2"/>
        <text text-anchor="middle" dy="4" font-size="10" fill="${tc.stroke}" font-weight="bold">${node.label?.slice(0, 6) || node.id.slice(0, 4)}</text>
      </g>`;
  });

  svg.innerHTML = svgContent;

  svg.querySelectorAll('.graph-node').forEach(g => {
    g.addEventListener('click', () => {
      const node = nodes.find(n => n.id === g.dataset.id);
      const sidebar = document.getElementById('kg-sidebar');
      const detail = document.getElementById('kg-detail');
      if (!node || !sidebar || !detail) return;
      sidebar.classList.remove('translate-x-full');
      const tc = TYPE_COLORS[node.type] || TYPE_COLORS.entity;
      detail.innerHTML = `
        <div class="w-12 h-12 rounded-lg flex items-center justify-center mb-4" style="background:${tc.stroke}15">
          <span class="material-symbols-outlined" style="color:${tc.stroke}">${tc.icon}</span>
        </div>
        <h4 class="font-bold text-lg">${node.label || node.id}</h4>
        <p class="text-xs font-mono text-outline mt-1">${node.type}</p>
        ${node.properties?.description ? `<p class="text-sm text-on-surface-variant mt-4 leading-relaxed">${node.properties.description}</p>` : ''}`;
    });
  });
}
