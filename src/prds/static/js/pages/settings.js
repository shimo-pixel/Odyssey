import { pageShell } from '../layout.js';

const PREFS_KEY = 'prds_prefs';

export function getPrefs() {
  try {
    return { ...defaultPrefs(), ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') };
  } catch {
    return defaultPrefs();
  }
}

function defaultPrefs() {
  return {
    useMock: true,
    defaultAgentCount: 10,
    defaultPeriods: 6,
    periodTimeUnit: 'month',
    periodTimeLength: 1,
    simulationStartDate: '',
    autoOpenResults: true,
  };
}

export function savePrefs(prefs) {
  localStorage.setItem(PREFS_KEY, JSON.stringify({ ...getPrefs(), ...prefs }));
}

export function renderSettings() {
  const prefs = getPrefs();
  return pageShell(`
    <div class="p-8 lg:p-12 max-w-3xl mx-auto pb-20">
      <header class="mb-10">
        <span class="text-xs text-primary font-bold uppercase tracking-widest">Preferences</span>
        <h1 class="text-3xl font-bold mt-2 text-on-surface">设置</h1>
        <p class="text-on-surface-variant mt-2">本地偏好与服务连接状态（保存在浏览器）</p>
      </header>

      <form id="settings-form" class="space-y-8">
        <section class="glass-panel bg-white rounded-xl overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-variant bg-surface-container-low">
            <h2 class="font-bold flex items-center gap-2">
              <span class="material-symbols-outlined text-primary">link</span>连接
            </h2>
          </div>
          <div class="p-6 space-y-4">
            <div id="conn-status" class="flex items-center justify-between p-4 rounded-lg bg-surface-container-low">
              <div><p class="text-sm font-medium">LLM 服务</p><p class="text-xs text-on-surface-variant" id="conn-detail">检测中…</p></div>
              <span id="conn-badge" class="text-xs font-bold px-2 py-1 rounded-full bg-surface-variant">—</span>
            </div>
            <label class="toggle-mock inline-flex w-full justify-between">
              <span>默认使用 Mock 模式（无需 API Key）</span>
              <input type="checkbox" name="useMock" ${prefs.useMock ? 'checked' : ''} />
            </label>
            <p class="text-xs text-on-surface-variant">真实 LLM 需在服务端 .env 配置 OPENAI_API_KEY</p>
          </div>
        </section>

        <section class="glass-panel bg-white rounded-xl overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-variant bg-surface-container-low">
            <h2 class="font-bold flex items-center gap-2">
              <span class="material-symbols-outlined text-secondary">tune</span>默认推演参数
            </h2>
          </div>
          <div class="p-6 space-y-5">
            <div class="config-chip">
              <div class="flex justify-between"><span class="text-sm font-medium">平行路径数量</span><span id="set-agent-val" class="font-mono font-bold text-primary">${prefs.defaultAgentCount}</span></div>
              <input type="range" name="defaultAgentCount" min="5" max="100" value="${prefs.defaultAgentCount}" id="set-agent-range"/>
            </div>
            <div class="config-chip">
              <div class="flex justify-between"><span class="text-sm font-medium">推演周期</span><span id="set-period-val" class="font-mono font-bold text-primary">${prefs.defaultPeriods}</span></div>
              <input type="range" name="defaultPeriods" min="3" max="24" value="${prefs.defaultPeriods}" id="set-period-range"/>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="text-xs font-bold text-on-surface-variant">周期单位</label>
                <select name="periodTimeUnit" class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-white">
                  <option value="day" ${prefs.periodTimeUnit === 'day' ? 'selected' : ''}>天</option>
                  <option value="week" ${prefs.periodTimeUnit === 'week' ? 'selected' : ''}>周</option>
                  <option value="month" ${prefs.periodTimeUnit === 'month' ? 'selected' : ''}>月</option>
                  <option value="quarter" ${prefs.periodTimeUnit === 'quarter' ? 'selected' : ''}>季度</option>
                  <option value="year" ${prefs.periodTimeUnit === 'year' ? 'selected' : ''}>年</option>
                </select>
              </div>
              <div>
                <label class="text-xs font-bold text-on-surface-variant">每周期长度</label>
                <input type="number" name="periodTimeLength" min="1" max="52" value="${prefs.periodTimeLength || 1}"
                  class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-white px-3 py-2"/>
              </div>
            </div>
            <div>
              <label class="text-xs font-bold text-on-surface-variant">起始日期（可选）</label>
              <input type="date" name="simulationStartDate" value="${prefs.simulationStartDate || ''}"
                class="mt-1.5 w-full text-sm rounded-lg border-outline-variant bg-white px-3 py-2"/>
            </div>
            <label class="flex items-center gap-3 text-sm cursor-pointer">
              <input type="checkbox" name="autoOpenResults" ${prefs.autoOpenResults ? 'checked' : ''} class="rounded accent-primary"/>
              推演完成后自动打开决策结果
            </label>
          </div>
        </section>

        <section class="glass-panel bg-white rounded-xl overflow-hidden">
          <div class="px-6 py-4 border-b border-outline-variant bg-surface-container-low">
            <h2 class="font-bold flex items-center gap-2">
              <span class="material-symbols-outlined text-tertiary">storage</span>数据
            </h2>
          </div>
          <div class="p-6 space-y-3">
            <div class="flex justify-between items-center text-sm">
              <span class="text-on-surface-variant">最近推演 ID</span>
              <code id="last-sim-id" class="text-xs font-mono bg-surface-container px-2 py-1 rounded">—</code>
            </div>
            <button type="button" id="clear-sim-btn" class="text-sm text-error hover:underline">清除本地推演记录</button>
          </div>
        </section>

        <section class="glass-panel bg-white rounded-xl p-6">
          <h2 class="font-bold text-sm text-on-surface-variant uppercase tracking-wider mb-2">关于</h2>
          <p class="text-sm text-on-surface">Odyssey PRDS v0.1.0</p>
          <p class="text-xs text-on-surface-variant mt-1">Parallel Reality Decision Simulator — 平行世界决策推演引擎</p>
        </section>

        <div class="flex justify-end gap-3">
          <button type="button" id="reset-btn" class="px-5 py-2.5 rounded-lg border border-outline-variant text-sm font-medium hover:bg-surface-container">恢复默认</button>
          <button type="submit" class="btn-start px-8 py-2.5 rounded-lg text-sm font-bold text-on-primary">保存设置</button>
        </div>
      </form>
      <p id="save-toast" class="fixed bottom-6 right-6 hidden bg-secondary text-white text-sm font-bold px-4 py-2 rounded-lg shadow-lg">已保存</p>
    </div>
  `, { topNav: 'settings', noSidebar: true, mainClass: 'mt-16 min-h-screen' });
}

export function mountSettings() {
  const form = document.getElementById('settings-form');
  const lastId = localStorage.getItem('prds_last_sim');
  document.getElementById('last-sim-id').textContent = lastId ? lastId.slice(0, 13) + '…' : '无';

  fetch('/health').then(r => r.json()).then(h => {
    const badge = document.getElementById('conn-badge');
    const detail = document.getElementById('conn-detail');
    if (h.llm_configured) {
      badge.textContent = '已连接';
      badge.className = 'text-xs font-bold px-2 py-1 rounded-full bg-secondary/15 text-secondary';
      detail.textContent = '服务端 API Key 已配置';
    } else {
      badge.textContent = 'Mock';
      badge.className = 'text-xs font-bold px-2 py-1 rounded-full bg-tertiary/15 text-tertiary';
      detail.textContent = '未检测到 API Key，建议使用 Mock 模式';
    }
  }).catch(() => {});

  document.getElementById('set-agent-range')?.addEventListener('input', e => {
    document.getElementById('set-agent-val').textContent = e.target.value;
  });
  document.getElementById('set-period-range')?.addEventListener('input', e => {
    document.getElementById('set-period-val').textContent = e.target.value;
  });

  document.getElementById('clear-sim-btn')?.addEventListener('click', () => {
    localStorage.removeItem('prds_last_sim');
    document.getElementById('last-sim-id').textContent = '无';
  });

  document.getElementById('reset-btn')?.addEventListener('click', () => {
    savePrefs(defaultPrefs());
    location.reload();
  });

  form?.addEventListener('submit', e => {
    e.preventDefault();
    const fd = new FormData(form);
    savePrefs({
      useMock: fd.get('useMock') === 'on',
      defaultAgentCount: Number(fd.get('defaultAgentCount')),
      defaultPeriods: Number(fd.get('defaultPeriods')),
      periodTimeUnit: fd.get('periodTimeUnit') || 'month',
      periodTimeLength: Number(fd.get('periodTimeLength')) || 1,
      simulationStartDate: fd.get('simulationStartDate') || '',
      autoOpenResults: fd.get('autoOpenResults') === 'on',
    });
    const toast = document.getElementById('save-toast');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2000);
  });
}

export function applyPrefsToSimulateForm(form) {
  const prefs = getPrefs();
  const agent = form.querySelector('[name="agentCount"]');
  const periods = form.querySelector('[name="periods"]');
  const mock = form.querySelector('[name="useMock"]');
  const unit = form.querySelector('[name="periodTimeUnit"]');
  const length = form.querySelector('[name="periodTimeLength"]');
  const startDate = form.querySelector('[name="simulationStartDate"]');
  if (agent) { agent.value = prefs.defaultAgentCount; agent.dispatchEvent(new Event('input')); }
  if (periods) { periods.value = prefs.defaultPeriods; periods.dispatchEvent(new Event('input')); }
  if (mock) mock.checked = prefs.useMock;
  if (unit) unit.value = prefs.periodTimeUnit || 'month';
  if (length) length.value = prefs.periodTimeLength || 1;
  if (startDate) startDate.value = prefs.simulationStartDate || '';
}
