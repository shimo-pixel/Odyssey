import { API, PHASE_LABELS, STATUS_LABELS, EVENT_CATEGORIES } from '../api.js';
import { pageShell } from '../layout.js';
import { getPrefs } from './settings.js';
import { formatPeriodLabel, timeConfigFrom } from '../time.js';

let cleanup = null;

export function renderMonitor(simId) {
  return pageShell(`
    <div class="flex flex-col h-[calc(100vh-64px)] overflow-hidden">
      <header class="h-20 border-b border-outline-variant flex items-center px-6 lg:px-8 gap-6 bg-surface/80 backdrop-blur-sm shrink-0">
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-center mb-2">
            <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">推演进度</span>
            <span id="prog-pct" class="font-mono text-sm font-bold text-primary">0%</span>
          </div>
          <div class="h-1.5 bg-surface-container rounded-full overflow-hidden">
            <div id="prog-bar" class="h-full bg-primary transition-all duration-500" style="width:0%"></div>
          </div>
        </div>
        <div class="flex items-center gap-6 shrink-0 border-l border-outline-variant pl-6">
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">决策周期</p><p id="stat-period" class="font-mono text-lg font-bold">0</p></div>
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">活跃路径</p><p id="stat-alive" class="font-mono text-lg font-bold text-secondary">—</p></div>
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">状态</p><p id="stat-status" class="font-mono text-sm font-bold text-tertiary">—</p></div>
        </div>
        <div id="pause-controls" class="shrink-0 flex items-center gap-2">
          <button type="button" id="pause-btn" class="hidden monitor-btn monitor-btn-outline">
            <span class="material-symbols-outlined text-base">pause</span>暂停
          </button>
          <button type="button" id="resume-btn" class="hidden monitor-btn monitor-btn-primary">
            <span class="material-symbols-outlined text-base">play_arrow</span>继续推演
          </button>
        </div>
      </header>
      <div class="flex-1 relative canvas-grid flex min-h-0">
        <div class="flex-1 relative overflow-hidden flex items-center justify-center">
          <div id="running-view" class="text-center p-8 max-w-md">
            <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <span id="running-icon" class="material-symbols-outlined text-primary text-3xl animate-pulse">hub</span>
            </div>
            <h3 id="running-title" class="font-bold text-lg mb-2">平行世界推演中</h3>
            <p id="running-desc" class="text-sm text-on-surface-variant">每条路径在相同初始条件下，面对随机事件逐步做出独立选择</p>
            <p id="pause-hint" class="hidden text-xs text-tertiary mt-3 font-medium">暂停请求已发出，将在当前周期结束后暂停…</p>
            <div id="live-feed" class="mt-6 text-left space-y-2"></div>
          </div>
          <div id="paused-view" class="hidden absolute inset-0 flex items-center justify-center p-8 bg-surface/60 backdrop-blur-sm">
            <div class="max-w-lg text-center glass-panel bg-white p-8 rounded-2xl">
              <span class="material-symbols-outlined text-tertiary text-4xl mb-3">pause_circle</span>
              <h3 class="font-bold text-xl mb-2">推演已暂停</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed">请在右侧面板添加您已遇到或预期可能发生的事件，完成后点击「继续推演」注入下一周期。</p>
            </div>
          </div>
        </div>
        <aside id="monitor-aside" class="w-96 border-l border-outline-variant bg-surface-container-lowest/90 flex flex-col shrink-0">
          <div id="aside-normal" class="flex flex-col flex-1 min-h-0">
            <div class="p-6 border-b border-outline-variant">
              <h3 class="text-sm font-bold">路径状态</h3>
              <p class="text-[11px] text-on-surface-variant mt-1">推演完成后可查看逐步决策矩阵</p>
            </div>
            <div id="rank-list" class="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-3">
              <p class="text-sm text-on-surface-variant text-center py-8">等待决策数据…</p>
            </div>
          </div>
          <div id="aside-paused" class="hidden flex flex-col flex-1 min-h-0">
            <div class="p-5 border-b border-outline-variant bg-tertiary/5">
              <h3 class="text-sm font-bold flex items-center gap-2">
                <span class="material-symbols-outlined text-tertiary text-lg">edit_note</span>注入自定义事件
              </h3>
              <p class="text-[11px] text-on-surface-variant mt-1">描述真实或预期情况，将在下一周期加入世界状态</p>
            </div>
            <form id="event-form" class="p-5 space-y-4 border-b border-outline-variant">
              <div>
                <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider">事件描述</label>
                <textarea name="description" rows="3" required maxlength="500"
                  placeholder="例如：主要竞争对手宣布降价 30%；或：团队核心成员可能离职…"
                  class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-white resize-none"></textarea>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="text-xs font-bold text-on-surface-variant">类别</label>
                  <select name="category" class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-white">
                    ${Object.entries(EVENT_CATEGORIES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}
                  </select>
                </div>
                <div>
                  <label class="text-xs font-bold text-on-surface-variant">影响方向</label>
                  <select name="impactPreset" class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-white">
                    <option value="-0.5">不利 (−)</option>
                    <option value="0">中性</option>
                    <option value="0.4" selected>有利 (+)</option>
                  </select>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-xs mb-1">
                  <span class="font-bold text-on-surface-variant">严重程度</span>
                  <span id="evt-severity-val" class="font-mono font-bold text-primary">0.6</span>
                </div>
                <input type="range" name="severity" min="0.1" max="1" step="0.1" value="0.6" class="w-full accent-primary"/>
              </div>
              <button type="submit" class="w-full monitor-btn monitor-btn-primary justify-center">
                <span class="material-symbols-outlined text-base">add</span>添加事件
              </button>
            </form>
            <div class="px-5 py-3 flex items-center justify-between border-b border-outline-variant">
              <span class="text-xs font-bold text-on-surface-variant">待注入 (<span id="evt-count">0</span>)</span>
              <button type="button" id="clear-events-btn" class="text-xs text-error hover:underline">清空</button>
            </div>
            <div id="event-list" class="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-2">
              <p class="text-xs text-on-surface-variant text-center py-6">尚未添加事件</p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  `, { topNav: 'simulate', sidebarActive: 'monitor', simId, mainClass: 'ml-64 mt-16' });
}

export function mountMonitor(simId) {
  if (cleanup) cleanup();
  let lastPeriod = 0;
  let isPaused = false;
  let timeConfig = timeConfigFrom();

  const pauseBtn = document.getElementById('pause-btn');
  const resumeBtn = document.getElementById('resume-btn');
  const eventForm = document.getElementById('event-form');

  pauseBtn?.addEventListener('click', async () => {
    pauseBtn.disabled = true;
    try {
      await API.pauseSimulation(simId);
      document.getElementById('pause-hint')?.classList.remove('hidden');
      pauseBtn.textContent = '等待暂停…';
    } catch (e) {
      alert(e.message || '暂停失败');
      pauseBtn.disabled = false;
    }
  });

  resumeBtn?.addEventListener('click', async () => {
    resumeBtn.disabled = true;
    try {
      await API.resumeSimulation(simId);
    } catch (e) {
      alert(e.message || '继续失败');
      resumeBtn.disabled = false;
    }
  });

  eventForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(eventForm);
    const payload = {
      description: fd.get('description'),
      category: fd.get('category'),
      impact: Number(fd.get('impactPreset')),
      severity: Number(fd.get('severity')),
    };
    try {
      await API.addUserEvent(simId, payload);
      eventForm.reset();
      eventForm.querySelector('[name="severity"]').value = '0.6';
      document.getElementById('evt-severity-val').textContent = '0.6';
      await refreshEventList(simId);
    } catch (err) {
      alert(err.message || '添加失败');
    }
  });

  eventForm?.querySelector('[name="severity"]')?.addEventListener('input', (e) => {
    document.getElementById('evt-severity-val').textContent = e.target.value;
  });

  document.getElementById('clear-events-btn')?.addEventListener('click', async () => {
    try {
      await API.clearUserEvents(simId);
      await refreshEventList(simId);
    } catch (err) {
      alert(err.message || '清空失败');
    }
  });

  cleanup = API.pollStatus(simId, async (data) => {
    timeConfig = timeConfigFrom(data);
    document.getElementById('prog-pct').textContent = `${Math.round(data.progress_pct)}%`;
    document.getElementById('prog-bar').style.width = `${data.progress_pct}%`;
    const periodLabel = data.current_period > 0
      ? formatPeriodLabel(data.current_period, timeConfig)
      : '—';
    document.getElementById('stat-period').innerHTML = data.current_period > 0
      ? `<span class="block text-sm leading-tight">${periodLabel.split(' · ')[0]}</span><span class="text-[10px] text-on-surface-variant font-normal">T${data.current_period} / ${data.total_periods}</span>`
      : `0 / ${data.total_periods}`;
    document.getElementById('stat-alive').textContent = `${data.alive_agents} / ${data.total_agents}`;
    document.getElementById('stat-status').textContent = STATUS_LABELS[data.status] || data.status;

    const canPause = data.status === 'running' && data.phase === 'simulation';
    const nowPaused = data.status === 'paused';
    const pausePending = data.pause_pending;

    pauseBtn?.classList.toggle('hidden', !canPause && !pausePending);
    resumeBtn?.classList.toggle('hidden', !nowPaused);

    if (canPause && !pausePending) {
      pauseBtn.disabled = false;
      pauseBtn.innerHTML = '<span class="material-symbols-outlined text-base">pause</span>暂停';
    }

    document.getElementById('pause-hint')?.classList.toggle('hidden', !pausePending || nowPaused);
    document.getElementById('paused-view')?.classList.toggle('hidden', !nowPaused);
    document.getElementById('aside-normal')?.classList.toggle('hidden', nowPaused);
    document.getElementById('aside-paused')?.classList.toggle('hidden', !nowPaused);

    if (nowPaused && !isPaused) {
      isPaused = true;
      await refreshEventList(simId);
      document.getElementById('running-title').textContent = '推演已暂停';
      document.getElementById('running-desc').textContent = '添加自定义事件后点击继续推演';
      document.getElementById('running-icon').textContent = 'pause_circle';
      document.getElementById('running-icon').classList.remove('animate-pulse');
    } else if (!nowPaused && isPaused) {
      isPaused = false;
      resumeBtn.disabled = false;
      document.getElementById('running-title').textContent = '平行世界推演中';
      document.getElementById('running-desc').textContent = '每条路径在相同初始条件下，面对随机事件逐步做出独立选择';
      document.getElementById('running-icon').textContent = 'hub';
      document.getElementById('running-icon').classList.add('animate-pulse');
    }

    if (data.current_period > lastPeriod && data.phase === 'simulation') {
      lastPeriod = data.current_period;
      const tag = data.status === 'paused' ? '暂停于' : '完成';
      appendFeed(`${formatPeriodLabel(data.current_period, timeConfig)}: ${data.alive_agents} 条路径在本周期${tag}决策`);
    }

    if (data.status === 'completed') {
      document.getElementById('rank-list').innerHTML = `
        <div class="p-4 rounded-xl bg-primary/5 border border-primary/20 text-center">
          <p class="text-sm font-bold text-primary">推演完成</p>
          <p class="text-xs text-on-surface-variant mt-2">正在加载决策矩阵…</p>
        </div>`;
      pauseBtn?.classList.add('hidden');
      resumeBtn?.classList.add('hidden');
      if (getPrefs().autoOpenResults !== false) {
        setTimeout(() => { location.hash = `#results/${simId}`; }, 600);
      }
    } else if (data.status === 'failed') {
      document.getElementById('rank-list').innerHTML = `<p class="text-error text-sm p-4">${data.error || '失败'}</p>`;
      pauseBtn?.classList.add('hidden');
      resumeBtn?.classList.add('hidden');
    }
  });
}

async function refreshEventList(simId) {
  try {
    const { events } = await API.getUserEvents(simId);
    document.getElementById('evt-count').textContent = events.length;
    const list = document.getElementById('event-list');
    if (!events.length) {
      list.innerHTML = '<p class="text-xs text-on-surface-variant text-center py-6">尚未添加事件</p>';
      return;
    }
    list.innerHTML = events.map((ev, i) => `
      <div class="p-3 rounded-lg bg-white border border-outline-variant text-sm">
        <div class="flex items-start gap-2">
          <span class="font-mono text-[10px] text-primary font-bold shrink-0">${i + 1}</span>
          <div class="min-w-0">
            <p class="font-medium text-on-surface leading-snug">${escapeHtml(ev.description)}</p>
            <p class="text-[10px] text-on-surface-variant mt-1">
              ${EVENT_CATEGORIES[ev.category] || ev.category}
              · 影响 ${ev.impact >= 0 ? '+' : ''}${ev.impact.toFixed(1)}
              · 严重 ${ev.severity.toFixed(1)}
            </p>
          </div>
        </div>
      </div>`).join('');
  } catch (_) {}
}

function appendFeed(msg) {
  const feed = document.getElementById('live-feed');
  if (!feed) return;
  const el = document.createElement('div');
  el.className = 'text-xs font-mono text-on-surface-variant bg-white border border-outline-variant rounded-lg px-3 py-2';
  el.textContent = msg;
  feed.prepend(el);
  if (feed.children.length > 5) feed.lastChild.remove();
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export function unmountMonitor() {
  if (cleanup) { cleanup(); cleanup = null; }
}
