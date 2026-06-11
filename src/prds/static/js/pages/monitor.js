import { API, statusLabel, getEventCategories } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import { getPrefs } from '../prefs.js';
import { icon } from '../icons.js';

let cleanup = null;

export function renderMonitor(simId) {
  const cats = getEventCategories();
  return pageShell(`
    <div class="flex flex-col h-screen overflow-hidden bg-background">
      <header class="h-16 border-b border-outline-variant flex items-center px-6 lg:px-8 gap-6 bg-surface/95 backdrop-blur-sm shrink-0">
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-center mb-2">
            <span class="text-xs font-medium text-on-surface-variant">${t('monitor.progress')}</span>
            <span id="prog-pct" class="font-mono text-sm font-semibold text-primary">0%</span>
          </div>
          <div class="h-1.5 bg-surface-container rounded-full overflow-hidden">
            <div id="prog-bar" class="h-full transition-all duration-500 rounded-full" style="width:0%;background:linear-gradient(90deg,var(--tone-blue),var(--tone-green))"></div>
          </div>
        </div>
        <div class="flex items-center gap-6 shrink-0 border-l border-outline-variant pl-6">
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">${t('monitor.event')}</p><p id="stat-event" class="font-mono text-lg font-bold">0</p></div>
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">${t('monitor.alive')}</p><p id="stat-alive" class="font-mono text-lg font-bold text-secondary">—</p></div>
          <div class="text-center"><p class="text-[10px] text-on-surface-variant font-bold">${t('monitor.status')}</p><p id="stat-status" class="font-mono text-sm font-bold text-tertiary">—</p></div>
        </div>
        <div id="pause-controls" class="shrink-0 flex items-center gap-2">
          <button type="button" id="pause-btn" class="hidden monitor-btn monitor-btn-outline">
            ${icon('pause', 'icon icon--sm')}${t('monitor.pause')}
          </button>
          <button type="button" id="resume-btn" class="hidden monitor-btn monitor-btn-primary">
            ${icon('play', 'icon icon--sm')}${t('monitor.resume')}
          </button>
        </div>
      </header>
      <div class="flex-1 relative canvas-grid flex min-h-0">
        <div class="flex-1 relative overflow-hidden flex items-center justify-center">
          <div id="running-view" class="text-center p-8 max-w-md">
            <div class="w-14 h-14 rounded-lg flex items-center justify-center mx-auto mb-4 bg-surface-container border border-outline-variant">
              <span id="running-icon">${icon('layers', 'icon icon--xl text-primary')}</span>
            </div>
            <h3 id="running-title" class="font-semibold text-base mb-2">${t('monitor.running')}</h3>
            <p id="running-desc" class="text-sm text-on-surface-variant">${t('monitor.runningDesc')}</p>
            <p id="pause-hint" class="hidden text-xs text-tertiary mt-3 font-medium">${t('monitor.pausePending')}</p>
            <div id="live-feed" class="mt-6 text-left space-y-2"></div>
          </div>
          <div id="paused-view" class="hidden absolute inset-0 flex items-center justify-center p-8 bg-surface/60 backdrop-blur-sm">
            <div class="max-w-lg text-center glass-panel p-8 rounded-lg">
              ${icon('pause', 'icon icon--xl text-on-surface-variant mx-auto mb-3')}
              <h3 class="font-semibold text-lg mb-2">${t('monitor.paused')}</h3>
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
              <h3 class="text-sm font-medium flex items-center gap-2">
                ${icon('edit', 'icon icon--md text-primary')}${t('monitor.injectEvent')}
              </h3>
              <p class="text-[11px] text-on-surface-variant mt-1">${t('monitor.injectHint')}</p>
            </div>
            <form id="event-form" class="p-5 space-y-4 border-b border-outline-variant">
              <div>
                <label class="text-xs font-medium text-on-surface-variant">${t('monitor.eventDesc')}</label>
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
                ${icon('add', 'icon icon--sm')}${t('monitor.addEvent')}
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
  `, { sidebarActive: 'monitor', simId, mainClass: 'ml-[13.5rem]' });
}

function pauseBtnHtml(waiting = false) {
  return `${icon('pause', 'icon icon--sm')}${waiting ? t('monitor.waitPause') : t('monitor.pause')}`;
}

function setRunningIcon(name) {
  const el = document.getElementById('running-icon');
  if (el) el.innerHTML = icon(name, 'icon icon--xl text-primary');
}

export function mountMonitor(simId) {
  if (cleanup) cleanup();
  let lastEventIndex = 0;
  let isPaused = false;

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
    document.getElementById('prog-pct').textContent = `${Math.round(data.progress_pct)}%`;
    document.getElementById('prog-bar').style.width = `${data.progress_pct}%`;
    document.getElementById('stat-event').textContent = data.current_event_index > 0
      ? `${data.current_event_index} / ${data.total_events}`
      : `0 / ${data.total_events}`;
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
      setRunningIcon('pause');
    } else if (!nowPaused && isPaused) {
      isPaused = false;
      resumeBtn.disabled = false;
      document.getElementById('running-title').textContent = t('monitor.running');
      document.getElementById('running-desc').textContent = t('monitor.runningDesc');
      setRunningIcon('layers');
    }

    if (data.current_event_index > lastEventIndex && data.phase === 'simulation') {
      lastEventIndex = data.current_event_index;
      const label = t('unit.eventNth', { n: data.current_event_index });
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
