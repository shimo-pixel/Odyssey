import { API, statusLabel, phaseLabel, TERMINAL_STATUSES, issueLabel } from '../api.js';
import { pageShell } from '../layout.js';
import { t } from '../i18n.js';
import { mountResults } from './results.js';

let pollTimer = null;
let statusStop = null;

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusChipClass(status) {
  const s = (status || '').toLowerCase();
  if (s === 'completed') return 'g-chip g-chip-green';
  if (s === 'failed') return 'g-chip g-chip-blue';
  return 'g-chip g-chip-blue';
}

function progressBarHtml(pct) {
  const w = Math.max(0, Math.min(100, Number(pct) || 0));
  return `
    <div class="h-1.5 bg-surface-container rounded-full overflow-hidden mt-3">
      <div class="h-full rounded-full" style="width:${w}%;background:linear-gradient(90deg,var(--tone-blue),var(--tone-green))"></div>
    </div>`;
}

export function renderHistory(simId = null) {
  if (simId) {
    return pageShell(`
      <div class="p-6 lg:p-10 max-w-[1400px] mx-auto" id="history-detail-root">
        <div class="mb-4">
          <a href="#history" class="text-sm text-primary hover:underline">${t('history.backList')}</a>
        </div>
        <div id="results-root">
          <div class="flex items-center justify-center py-24">
            <div class="animate-pulse text-primary font-bold">${t('results.loading')}</div>
          </div>
        </div>
      </div>
    `, { sidebarActive: 'history', simId });
  }

  return pageShell(`
    <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20">
      <header class="mb-8">
        <h1 class="text-2xl font-semibold text-on-surface tracking-tight">${t('history.title')}</h1>
        <p class="text-sm text-on-surface-variant mt-2">${t('history.subtitle')}</p>
      </header>
      <div id="history-grid" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div class="glass-panel rounded-lg p-6 text-center text-on-surface-variant text-sm col-span-full">${t('common.loading')}</div>
      </div>
    </div>
  `, { sidebarActive: 'history' });
}

async function refreshHistoryList() {
  const grid = document.getElementById('history-grid');
  if (!grid) return;
  try {
    const data = await API.listSimulations();
    const items = data.simulations || [];
    if (!items.length) {
      grid.innerHTML = `<div class="glass-panel rounded-lg p-8 text-center text-on-surface-variant text-sm col-span-full">${t('history.empty')}</div>`;
      return;
    }
    grid.innerHTML = items.map((s) => `
      <a href="#history/${encodeURIComponent(s.id)}" class="glass-panel rounded-lg p-5 block hover:border-primary/40 transition-colors no-underline text-inherit">
        <div class="flex items-start justify-between gap-2 mb-2">
          <h3 class="font-semibold text-sm text-on-surface line-clamp-2">${escapeHtml(s.goal || t('history.untitled'))}</h3>
          <span class="text-[10px] font-medium px-2 py-0.5 rounded-md ${statusChipClass(s.status)} shrink-0">${escapeHtml(statusLabel(s.status))}</span>
        </div>
        <p class="text-xs text-on-surface-variant line-clamp-2 mb-3">${escapeHtml(s.background_preview || '—')}</p>
        <div class="flex flex-wrap gap-2 text-[11px] text-outline">
          <span>${escapeHtml(phaseLabel(s.phase))}</span>
          <span>·</span>
          <span>${t('history.agents', { n: s.agent_count || 0 })}</span>
          <span>·</span>
          <span>${Math.round(s.progress_pct || 0)}%</span>
        </div>
        ${['running', 'pending'].includes((s.status || '').toLowerCase()) ? progressBarHtml(s.progress_pct) : ''}
        <p class="text-xs mt-2">${escapeHtml(s.failure ? issueLabel(s.failure) : s.error || '')}</p>
        <p class="text-xs mt-2">${escapeHtml((s.warnings || []).map(issueLabel).join(' · '))}</p>
        <p class="text-[11px] text-outline mt-3">${formatTime(s.created_at)}</p>
      </a>
    `).join('');
  } catch (e) {
    grid.innerHTML = `<div class="glass-panel rounded-lg p-6 text-center text-error text-sm col-span-full">${escapeHtml(e.message || String(e))}</div>`;
  }
}

function renderRunningPanel(simId, status) {
  const pct = Math.round(status?.progress_pct || 0);
  const root = document.getElementById('results-root');
  if (!root) return;
  root.innerHTML = `
    <div class="glass-panel rounded-lg p-8 max-w-xl mx-auto text-center">
      <h2 class="text-lg font-semibold mb-2">${t('history.runningTitle')}</h2>
      <p class="text-sm text-on-surface-variant mb-6">${t('history.runningDesc')}</p>
      <div class="flex justify-between text-xs text-on-surface-variant mb-2">
        <span>${escapeHtml(statusLabel(status?.status))}</span>
        <span class="font-mono text-primary">${pct}%</span>
      </div>
      ${progressBarHtml(pct)}
      <div class="grid grid-cols-3 gap-4 mt-6 text-sm">
        <div><p class="text-[10px] text-on-surface-variant">${t('history.phase')}</p><p class="font-medium mt-1">${escapeHtml(phaseLabel(status?.phase))}</p></div>
        <div><p class="text-[10px] text-on-surface-variant">${t('monitor.event')}</p><p class="font-mono mt-1">${status?.current_event_index ?? 0}/${status?.total_events ?? 0}</p></div>
        <div><p class="text-[10px] text-on-surface-variant">${t('monitor.alive')}</p><p class="font-mono mt-1">${status?.alive_agents ?? '—'}</p></div>
      </div>
      ${status?.error ? `<p class="text-error text-sm mt-4">${escapeHtml(status.error)}</p>` : ''}
      <p class="text-[11px] font-mono text-outline mt-6">${escapeHtml(simId)}</p>
    </div>`;
}

export function unmountHistory() {
  if (statusStop) {
    statusStop();
    statusStop = null;
  }
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export async function mountHistory(simId = null) {
  unmountHistory();
  if (!simId) {
    await refreshHistoryList();
    pollTimer = setInterval(refreshHistoryList, 4000);
    return;
  }

  try {
    const status = await API.getStatus(simId);
    const st = (status.status || '').toLowerCase();
    if (st === 'completed') {
      await mountResults(simId);
      return;
    }
    if (TERMINAL_STATUSES.has(st)) {
      renderRunningPanel(simId, status);
      return;
    }
    renderRunningPanel(simId, status);
    statusStop = API.pollStatus(simId, async (data) => {
      const s = (data.status || '').toLowerCase();
      if (s === 'completed') {
        if (statusStop) {
          statusStop();
          statusStop = null;
        }
        await mountResults(simId);
        return;
      }
      renderRunningPanel(simId, data);
    });
  } catch (e) {
    const root = document.getElementById('results-root');
    if (root) {
      root.innerHTML = `<div class="glass-panel p-8 text-center"><p class="text-error font-bold">${t('results.loadFailed')}</p>
        <p class="text-sm text-on-surface-variant mt-2">${escapeHtml(e.message)}</p>
        <a href="#history" class="inline-block mt-4 text-primary font-bold">${t('history.backList')}</a></div>`;
    }
  }
}
