import { API, statusLabel, getEventCategories } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import { getPrefs } from '../prefs.js';
import { formatPeriodLabel, timeConfigFrom } from '../time.js';

let cleanup = null;

export function renderMonitor(simId) {
  const cats = getEventCategories();
  return pageShell(`
    <div class="flex flex-col h-screen overflow-hidden bg-background">
      <header class="h-20 border-b border-outline-variant flex items-center px-6 lg:px-8 gap-6 bg-surface/80 backdrop-blur-sm shrink-0">
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-center mb-2">
            <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">${t('monitor.progress')}</span>
            <span id="prog-pct" class="font-mono text-sm font-bold text-primary">0%</span>
          </div>
          <div class="h-1.5 bg-surface-container rounded-full overflow-hidden">
            <div id="prog-bar" class="h-full bg-primary transition-all duration-500" style="width:0%"></div>
          </div>
        </div>
        <div class="flex items-center gap-6 shrink-0 border-l border-outline-variant pl-6">
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">${t('monitor.period')}</p><p id="stat-period" class="font-mono text-lg font-bold">0</p></div>
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">${t('monitor.alive')}</p><p id="stat-alive" class="font-mono text-lg font-bold text-secondary">—</p></div>
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">${t('monitor.status')}</p><p id="stat-status" class="font-mono text-sm font-bold text-tertiary">—</p></div>
        </div>
        <div id="pause-controls" class="shrink-0 flex items-center gap-2">
          <button type="button" id="pause-btn" class="hidden monitor-btn monitor-btn-outline">
            <span class="material-symbols-outlined text-base">pause</span>${t('monitor.pause')}
          </button>
          <button type="button" id="resume-btn" class="hidden monitor-btn monitor-btn-primary">
            <span class="material-symbols-outlined text-base">play_arrow</span>${t('monitor.resume')}
          </button>
        </div>
      </header>
      <div class="flex-1 relative canvas-grid flex min-h-0">
        <div class="flex-1 relative overflow-hidden flex items-center justify-center">
          <div id="running-view" class="text-center p-8 max-w-md">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4" style="background:var(--g-blue-light)">
              <span id="running-icon" class="material-symbols-outlined text-primary text-3xl animate-pulse">hub</span>
            </div>
            <h3 id="running-title" class="font-bold text-lg mb-2">${t('monitor.running')}</h3>
            <p id="running-desc" class="text-sm text-on-surface-variant">${t('monitor.runningDesc')}</p>
            <p id="pause-hint" class="hidden text-xs text-tertiary mt-3 font-medium">${t('monitor.pausePending')}</p>
            <div id="live-feed" class="mt-6 text-left space-y-2"></div>
          </div>
          <div id="paused-view" class="hidden absolute inset-0 flex items-center justify-center p-8 bg-surface/60 backdrop-blur-sm">
            <div class="max-w-lg text-center glass-panel p-8 rounded-2xl">
              <span class="material-symbols-outlined text-tertiary text-4xl mb-3">pause_circle</span>
              <h3 class="font-bold text-xl mb-2">${t('monitor.paused')}</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed">${t('monitor.pausedDesc')}</p>
            </div>
          </div>
        </div>
        <aside id="monitor-aside" class="w-96 border-l border-outline-variant bg-surface-container-lowest/90 flex flex-col shrink-0">
          <div id="aside-normal" class="flex flex-col flex-1 min-h-0">
            <div class="p-6 border-b border-outline-variant">
              <h3 class="text-sm font-bold">${t('monitor.pathStatus')}</h3>
              <p class="text-[11px] text-on-surface-variant mt-1">${t('monitor.pathStatusHint')}</p>
            </div>
            <div id="rank-list" class="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-3">
              <p class="text-sm text-on-surface-variant text-center py-8">${t('monitor.waitData')}</p>
            </div>
          </div>
          <div id="aside-paused" class="hidden flex flex-col flex-1 min-h-0">
            <div class="p-5 border-b border-outline-variant bg-tertiary/5">
              <h3 class="text-sm font-bold flex items-center gap-2">
                <span class="material-symbols-outlined text-tertiary text-lg">edit_note</span>${t('monitor.injectEvent')}
              </h3>
              <p class="text-[11px] text-on-surface-variant mt-1">${t('monitor.injectHint')}</p>
            </div>
            <form id="event-form" class="p-5 space-y-4 border-b border-outline-variant">
              <div>
                <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider">${t('monitor.eventDesc')}</label>
                <textarea name="description" rows="3" required maxlength="500"
                  placeholder="${t('monitor.eventPlaceholder')}"
                  class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest resize-none"></textarea>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="text-xs font-bold text-on-surface-variant">${t('monitor.category')}</label>
                  <select name="category" class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest">
                    ${Object.entries(cats).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}
                  </select>
                </div>
                <div>
                  <label class="text-xs font-bold text-on-surface-variant">${t('monitor.impact')}</label>
                  <select name="impactPreset" class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest">
                    <option value="-0.5">${t('monitor.impact.bad')}</option>
                    <option value="0">${t('monitor.impact.neutral')}</option>
                    <option value="0.4" selected>${t('monitor.impact.good')}</option>
                  </select>
                </div>
              </div>
              <div>
                <div class="flex justify-between text-xs mb-1">
                  <span class="font-bold text-on-surface-variant">${t('monitor.severity')}</span>
                  <span id="evt-severity-val" class="font-mono font-bold text-primary">0.6</span>
                </div>
                <input type="range" name="severity" min="0.1" max="1" step="0.1" value="0.6" class="w-full accent-primary"/>
              </div>
              <button type="submit" class="w-full monitor-btn monitor-btn-primary justify-center">
                <span class="material-symbols-outlined text-base">add</span>${t('monitor.addEvent')}
              </button>
            </form>
            <div class="px-5 py-3 flex items-center justify-between border-b border-outline-variant">
              <span class="text-xs font-bold text-on-surface-variant">${t('monitor.pendingLabel')} (<span id="evt-count">0</span>)</span>
              <button type="button" id="clear-events-btn" class="text-xs text-error hover:underline">${t('monitor.clear')}</button>
            </div>
            <div id="event-list" class="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-2">
              <p class="text-xs text-on-surface-variant text-center py-6">${t('monitor.noEvents')}</p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  `, { sidebarActive: 'monitor', simId, mainClass: 'ml-60' });
}

function pauseBtnHtml(waiting = false) {
  if (waiting) {
    return `<span class="material-symbols-outlined text-base">pause</span>${t('monitor.waitPause')}`;
  }
  return `<span class="material-symbols-outlined text-base">pause</span>${t('monitor.pause')}`;
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
      pauseBtn.innerHTML = pauseBtnHtml(true);
    } catch (e) {
      alert(e.message || t('monitor.pauseFailed'));
      pauseBtn.disabled = false;
    }
  });

  resumeBtn?.addEventListener('click', async () => {
    resumeBtn.disabled = true;
    try {
      await API.resumeSimulation(simId);
    } catch (e) {
      alert(e.message || t('monitor.resumeFailed'));
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
      alert(err.message || t('monitor.addFailed'));
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
      alert(err.message || t('monitor.clearFailed'));
    }
  });

  cleanup = API.pollStatus(simId, async (data) => {
    timeConfig = timeConfigFrom(data);
    document.getElementById('prog-pct').textContent = `${Math.round(data.progress_pct)}%`;
    document.getElementById('prog-bar').style.width = `${data.progress_pct}%`;
    const periodLabel = data.current_period > 0
      ? formatPeriodLabel(data.current_period, timeConfig)
      : t('common.none');
    document.getElementById('stat-period').innerHTML = data.current_period > 0
      ? `<span class="block text-sm leading-tight">${periodLabel.split(' · ')[0]}</span><span class="text-[10px] text-on-surface-variant font-normal">T${data.current_period} / ${data.total_periods}</span>`
      : `0 / ${data.total_periods}`;
    document.getElementById('stat-alive').textContent = `${data.alive_agents} / ${data.total_agents}`;
    document.getElementById('stat-status').textContent = statusLabel(data.status);

    const canPause = data.status === 'running' && data.phase === 'simulation';
    const nowPaused = data.status === 'paused';
    const pausePending = data.pause_pending;

    pauseBtn?.classList.toggle('hidden', !canPause && !pausePending);
    resumeBtn?.classList.toggle('hidden', !nowPaused);

    if (canPause && !pausePending) {
      pauseBtn.disabled = false;
      pauseBtn.innerHTML = pauseBtnHtml(false);
    }

    document.getElementById('pause-hint')?.classList.toggle('hidden', !pausePending || nowPaused);
    document.getElementById('paused-view')?.classList.toggle('hidden', !nowPaused);
    document.getElementById('aside-normal')?.classList.toggle('hidden', nowPaused);
    document.getElementById('aside-paused')?.classList.toggle('hidden', !nowPaused);

    if (nowPaused && !isPaused) {
      isPaused = true;
      await refreshEventList(simId);
      document.getElementById('running-title').textContent = t('monitor.paused');
      document.getElementById('running-desc').textContent = t('monitor.pausedShort');
      document.getElementById('running-icon').textContent = 'pause_circle';
      document.getElementById('running-icon').classList.remove('animate-pulse');
    } else if (!nowPaused && isPaused) {
      isPaused = false;
      resumeBtn.disabled = false;
      document.getElementById('running-title').textContent = t('monitor.running');
      document.getElementById('running-desc').textContent = t('monitor.runningDesc');
      document.getElementById('running-icon').textContent = 'hub';
      document.getElementById('running-icon').classList.add('animate-pulse');
    }

    if (data.current_period > lastPeriod && data.phase === 'simulation') {
      lastPeriod = data.current_period;
      const label = formatPeriodLabel(data.current_period, timeConfig);
      const feedKey = data.status === 'paused' ? 'monitor.feedPaused' : 'monitor.feedDone';
      appendFeed(t(feedKey, { label, n: data.alive_agents }));
    }

    if (data.status === 'completed') {
      document.getElementById('rank-list').innerHTML = `
        <div class="p-4 rounded-xl bg-primary/5 border border-primary/20 text-center">
          <p class="text-sm font-bold text-primary">${t('monitor.complete')}</p>
          <p class="text-xs text-on-surface-variant mt-2">${t('monitor.loadingMatrix')}</p>
        </div>`;
      pauseBtn?.classList.add('hidden');
      resumeBtn?.classList.add('hidden');
      if (getPrefs().autoOpenResults !== false) {
        setTimeout(() => { location.hash = `#results/${simId}`; }, 600);
      }
    } else if (data.status === 'failed') {
      document.getElementById('rank-list').innerHTML = `<p class="text-error text-sm p-4">${data.error || t('status.failed')}</p>`;
      pauseBtn?.classList.add('hidden');
      resumeBtn?.classList.add('hidden');
    }
  });
}

async function refreshEventList(simId) {
  const cats = getEventCategories();
  try {
    const { events } = await API.getUserEvents(simId);
    const countEl = document.getElementById('evt-count');
    if (countEl) countEl.textContent = events.length;
    const list = document.getElementById('event-list');
    if (!events.length) {
      list.innerHTML = `<p class="text-xs text-on-surface-variant text-center py-6">${t('monitor.noEvents')}</p>`;
      return;
    }
    list.innerHTML = events.map((ev, i) => `
      <div class="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant text-sm">
        <div class="flex items-start gap-2">
          <span class="font-mono text-[10px] text-primary font-bold shrink-0">${i + 1}</span>
          <div class="min-w-0">
            <p class="font-medium text-on-surface leading-snug">${escapeHtml(ev.description)}</p>
            <p class="text-[10px] text-on-surface-variant mt-1">
              ${cats[ev.category] || ev.category}
              · ${ev.impact >= 0 ? '+' : ''}${ev.impact.toFixed(1)}
              · ${ev.severity.toFixed(1)}
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
  el.className = 'text-xs font-mono text-on-surface-variant bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2';
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
