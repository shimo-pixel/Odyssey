import { API } from '../api.js';
import { pageShell } from '../layout.js';

const TYPE_COLORS = {
  person: { stroke: '#4648d4', icon: 'person', label: '人员' },
  organization: { stroke: '#006c49', icon: 'corporate_fare', label: '组织' },
  product: { stroke: '#825100', icon: 'inventory_2', label: '产品' },
  capital: { stroke: '#494bd6', icon: 'payments', label: '资金' },
  market: { stroke: '#00714d', icon: 'storefront', label: '市场' },
  technology: { stroke: '#825100', icon: 'memory', label: '技术' },
  time: { stroke: '#767586', icon: 'schedule', label: '时间' },
  entity: { stroke: '#4648d4', icon: 'category', label: '实体' },
  risk: { stroke: '#ba1a1a', icon: 'warning', label: '风险' },
};

export function renderKnowledge(simId) {
  return pageShell(`
    <div class="mr-0 lg:mr-80 h-[calc(100vh-64px)] relative bg-surface-container-lowest overflow-hidden">
      <div class="absolute top-4 left-4 glass-panel p-4 rounded-lg z-20 max-w-xs">
        <h4 class="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">GraphRAG 世界背景</h4>
        <p id="kg-bg-summary" class="text-xs text-on-surface-variant leading-relaxed line-clamp-4">加载中…</p>
        <p id="kg-source" class="text-[10px] text-primary font-bold mt-2"></p>
      </div>
      <div class="absolute top-4 left-[280px] glass-panel p-4 rounded-lg z-20 hidden lg:block">
        <h4 class="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">实体类型</h4>
        <div class="flex flex-col gap-2 text-xs">
          ${Object.entries(TYPE_COLORS).slice(0, 4).map(([, v]) => `<div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full" style="background:${v.stroke}"></span>${v.label}</div>`).join('')}
        </div>
      </div>
      <div id="graph-viewport" class="w-full h-full">
        <svg id="kg-svg" class="w-full h-full" viewBox="0 0 1200 800"></svg>
      </div>
      <aside id="kg-sidebar" class="fixed right-0 top-16 h-[calc(100vh-64px)] w-80 bg-surface border-l border-outline-variant p-6 z-30 translate-x-full transition-transform overflow-y-auto custom-scrollbar">
        <div class="flex justify-between items-center mb-6">
          <h3 class="font-bold">节点详情</h3>
          <button id="kg-close" class="material-symbols-outlined text-on-surface-variant hover:text-on-surface">close</button>
        </div>
        <div id="kg-detail"><p class="text-sm text-on-surface-variant">点击节点查看详情</p></div>
      </aside>
      <div id="kg-empty" class="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div class="glass-panel p-8 text-center max-w-md pointer-events-auto">
          <p class="text-on-surface-variant mb-4" id="kg-msg">完成一次推演后，GraphRAG 知识图谱将在此展示。</p>
          <a href="#simulate" class="text-primary font-bold">开始模拟 →</a>
        </div>
      </div>
    </div>
  `, { topNav: 'simulate', sidebarActive: 'knowledge', simId, mainClass: 'ml-64 mt-16 min-h-screen' });
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
      document.getElementById('kg-msg').textContent = '推演进行中，GraphRAG 正在构建世界图谱…';
      document.querySelector('#kg-empty a').href = `#monitor/${id}`;
      document.querySelector('#kg-empty a').textContent = '查看进度 →';
      return;
    }
    const data = await API.getKnowledgeGraph(id);
    document.getElementById('kg-empty')?.classList.add('hidden');
    const bg = data.world_background || {};
    document.getElementById('kg-bg-summary').textContent = bg.summary || '暂无世界背景摘要';
    const source = bg.graph_source === 'graphrag' ? 'GraphRAG' : '本体抽取';
    const neo = bg.neo4j_persisted ? ' · Neo4j' : '';
    document.getElementById('kg-source').textContent = `${source}${neo}`;
    renderGraph(data.knowledge_graph, data.ontology, bg);
  } catch (e) {
    document.getElementById('kg-msg').textContent = '加载失败: ' + e.message;
  }
}

function renderGraph(kg, ontology, worldBackground) {
  const svg = document.getElementById('kg-svg');
  if (!svg || !kg?.nodes?.length) return;

  const nodes = kg.nodes.map((n, i) => {
    const angle = (i / kg.nodes.length) * Math.PI * 2;
    const r = 220 + (i % 3) * 40;
    return {
      ...n,
      x: 600 + Math.cos(angle) * r,
      y: 400 + Math.sin(angle) * r,
    };
  });
  const pos = Object.fromEntries(nodes.map(n => [n.id, n]));

  let html = '<defs><marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#767586"/></marker></defs>';
  html += '<g opacity="0.35">';
  (kg.edges || []).forEach(e => {
    const a = pos[e.source], b = pos[e.target];
    if (a && b) html += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#767586" stroke-width="1.5" marker-end="url(#arrow)" class="edge-line"/>`;
  });
  html += '</g><g>';
  nodes.forEach(n => {
    const t = TYPE_COLORS[n.entity_type] || TYPE_COLORS.entity;
    html += `<g class="graph-node" data-id="${n.id}" transform="translate(${n.x},${n.y})">
      <circle r="28" fill="#fff" stroke="${t.stroke}" stroke-width="2.5"/>
      <text class="material-symbols-outlined" fill="${t.stroke}" font-size="20" text-anchor="middle" y="6">${t.icon}</text>
      <text fill="#1c1b1d" font-size="11" font-weight="600" text-anchor="middle" y="44">${escapeHtml(n.name || n.id)}</text>
    </g>`;
  });
  html += '</g>';
  svg.innerHTML = html;

  svg.querySelectorAll('.graph-node').forEach(g => {
    g.addEventListener('click', () => showNode(g.dataset.id, nodes, kg.edges || [], ontology, worldBackground));
  });
}

function showNode(id, nodes, edges, ontology, worldBackground) {
  const n = nodes.find(x => x.id === id);
  if (!n) return;
  const t = TYPE_COLORS[n.entity_type] || TYPE_COLORS.entity;
  const rels = edges.filter(e => e.source === id || e.target === id);
  const entityReport = worldBackground?.entity_reports?.[id] || n.description || '';
  const sidebar = document.getElementById('kg-sidebar');
  document.getElementById('kg-detail').innerHTML = `
    <div class="flex items-center gap-3 mb-6">
      <div class="w-12 h-12 rounded-lg flex items-center justify-center" style="background:${t.stroke}15">
        <span class="material-symbols-outlined text-2xl" style="color:${t.stroke}">${t.icon}</span>
      </div>
      <div><h2 class="text-lg font-bold">${escapeHtml(n.name || id)}</h2><span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-surface-container">${t.label}</span></div>
    </div>
    ${entityReport ? `<p class="text-sm text-on-surface-variant mb-4 leading-relaxed">${escapeHtml(entityReport)}</p>` : ''}
    <div class="space-y-2 text-sm">
      ${Object.entries(n).filter(([k]) => !['id', 'name', 'entity_type', 'x', 'y', 'description', 'simulation_id'].includes(k)).map(([k, v]) =>
        `<div class="flex justify-between py-1 border-b border-outline-variant/30"><span class="text-on-surface-variant">${k}</span><span class="font-bold">${escapeHtml(String(v))}</span></div>`
      ).join('')}
    </div>
    ${rels.length ? `<div class="mt-6"><h4 class="text-xs font-bold uppercase text-on-surface-variant mb-3">关联实体</h4>${rels.map(e => {
      const other = e.source === id ? e.target : e.source;
      const on = nodes.find(x => x.id === other);
      return `<div class="p-3 bg-surface-container-low border rounded-lg mb-2 text-sm"><span class="font-medium">${escapeHtml(on?.name || other)}</span> <span class="text-[10px] text-outline">${e.relation_type || '关联'}</span></div>`;
    }).join('')}</div>` : ''}
    ${worldBackground?.community_summaries?.length ? `<div class="mt-4"><h4 class="text-xs font-bold text-primary uppercase mb-2">社区摘要</h4><ul class="text-xs space-y-2">${worldBackground.community_summaries.map(s => `<li class="text-on-surface-variant">• ${escapeHtml(s)}</li>`).join('')}</ul></div>` : ''}
    ${ontology?.risks?.length ? `<div class="mt-4"><h4 class="text-xs font-bold text-error uppercase mb-2">风险</h4><ul class="text-xs space-y-1">${ontology.risks.map(r => `<li>• ${escapeHtml(r)}</li>`).join('')}</ul></div>` : ''}
  `;
  sidebar.classList.remove('translate-x-full');
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function mountKnowledgeEmpty() {}
