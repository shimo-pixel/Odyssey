import { API, buildPayload, PHASE_STEPS } from '../api.js';
import { pageShell } from '../layout.js';
import { applyPrefsToSimulateForm } from './settings.js';
import { buildTimelinePreview, timeConfigFrom, unitLengthLabel } from '../time.js';

const PLACEHOLDER_BACKGROUND = `描述您当前的完整现状，例如：背景与环境、已有资源与能力、主要约束与风险、关键利益相关方……

适用于商业决策、个人规划、组织变革、政策推演等任意领域。`;

const PLACEHOLDER_GOAL = `描述您希望达成的最终目标，以及衡量成功的标准（自然语言即可）。`;

export function renderSimulate() {
  return pageShell(`
    <div class="pl-0 lg:pl-64 pr-0 lg:pr-[520px] pt-16 min-h-screen overflow-y-auto no-scrollbar bg-gradient-to-b from-background to-surface-container-low/30">
      <div class="p-8 lg:p-12 max-w-3xl mx-auto space-y-10 pb-24">

        <section class="simulate-hero p-8 lg:p-10">
          <div class="relative z-10">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider mb-4">
              <span class="material-symbols-outlined text-sm">hub</span>
              Parallel Reality Decision Simulator
            </div>
            <h1 class="text-3xl lg:text-4xl font-bold text-on-surface tracking-tight leading-tight">平行现实决策模拟器</h1>
            <p class="text-base text-on-surface-variant mt-3 leading-relaxed max-w-xl">
              在相同初始条件下，生成数百条平行路径。每条路径面对随机事件时独立做出选择——我们关注「在什么条件下选了什么」，而非智能体性格。
            </p>
          </div>
        </section>

        <form id="sim-form" class="space-y-8">
          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <span class="w-1 h-5 rounded-full bg-primary"></span>
              <label class="text-xs text-primary font-bold uppercase tracking-widest">当前现状</label>
            </div>
            <div class="input-panel overflow-hidden">
              <textarea id="background" name="background" class="w-full bg-transparent border-none focus:ring-0 p-6 text-sm leading-relaxed text-on-surface placeholder:text-outline/70"
                placeholder="${PLACEHOLDER_BACKGROUND.replace(/\n/g, '&#10;')}"></textarea>
              <div class="input-panel-footer px-4 py-2.5 flex items-center justify-between">
                <span class="text-[11px] text-on-surface-variant">支持任意领域的决策推演</span>
                <span id="bg-count" class="font-mono text-[11px] text-outline">0 字</span>
              </div>
            </div>
          </div>

          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <span class="w-1 h-5 rounded-full bg-secondary"></span>
              <label class="text-xs text-secondary font-bold uppercase tracking-widest">最终目标</label>
            </div>
            <div class="input-panel overflow-hidden">
              <div class="flex items-start gap-3 p-6 pb-0">
                <span class="material-symbols-outlined text-secondary mt-0.5 shrink-0">flag</span>
                <textarea id="goal" name="goal" rows="4" class="w-full bg-transparent border-none focus:ring-0 p-0 text-base leading-relaxed text-on-surface placeholder:text-outline/70 resize-none min-h-[100px]"
                  placeholder="${PLACEHOLDER_GOAL}"></textarea>
              </div>
              <div class="input-panel-footer px-4 py-2.5 flex justify-end">
                <span id="goal-count" class="font-mono text-[11px] text-outline">0 字</span>
              </div>
            </div>
          </div>

          <details class="group">
            <summary class="flex items-center gap-2 cursor-pointer text-sm font-medium text-on-surface-variant hover:text-primary transition-colors list-none">
              <span class="material-symbols-outlined text-lg group-open:rotate-90 transition-transform">chevron_right</span>
              环境约束（可选）
            </summary>
            <div class="mt-3 input-panel overflow-hidden">
              <textarea name="constraints" rows="3" class="w-full bg-transparent border-none focus:ring-0 p-5 text-sm text-on-surface placeholder:text-outline/80"
                placeholder="每行一条约束，例如：时间限制、预算上限、政策红线……"></textarea>
            </div>
          </details>

          <div class="pt-2 space-y-5">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-1 h-5 rounded-full bg-outline"></span>
              <span class="text-xs text-on-surface-variant font-bold uppercase tracking-widest">推演参数</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="config-chip">
                <div class="flex justify-between items-center">
                  <span class="text-sm font-medium text-on-surface">平行路径数量</span>
                  <span id="agent-val" class="font-mono text-sm font-bold text-primary">10</span>
                </div>
                <input type="range" name="agentCount" min="5" max="100" value="10" id="agent-range"/>
                <span class="text-[10px] text-on-surface-variant">更多路径 = 更全面的选择空间探索</span>
              </div>
              <div class="config-chip">
                <div class="flex justify-between items-center">
                  <span class="text-sm font-medium text-on-surface">推演周期</span>
                  <span id="period-val" class="font-mono text-sm font-bold text-primary">6</span>
                </div>
                <input type="range" name="periods" min="3" max="24" value="6" id="period-range"/>
                <span class="text-[10px] text-on-surface-variant">共多少个决策时间步</span>
              </div>
            </div>
            <div class="glass-panel bg-white rounded-xl p-4 space-y-4 border border-outline-variant/80">
              <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-primary text-lg">schedule</span>
                <span class="text-sm font-bold text-on-surface">周期时间</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase">时间单位</label>
                  <select name="periodTimeUnit" id="period-time-unit" class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2">
                    <option value="day">天</option>
                    <option value="week">周</option>
                    <option value="month" selected>月</option>
                    <option value="quarter">季度</option>
                    <option value="year">年</option>
                  </select>
                </div>
                <div>
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase">每周期长度</label>
                  <input type="number" name="periodTimeLength" id="period-time-length" min="1" max="52" value="1"
                    class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2"/>
                </div>
                <div>
                  <label class="text-[10px] font-bold text-on-surface-variant uppercase">起始日期（可选）</label>
                  <input type="date" name="simulationStartDate" id="simulation-start-date"
                    class="mt-1 w-full text-sm rounded-lg border-outline-variant bg-surface-container-lowest px-3 py-2"/>
                </div>
              </div>
              <p id="period-time-desc" class="text-[11px] text-on-surface-variant">每周期 1 月</p>
              <div>
                <p class="text-[10px] font-bold text-on-surface-variant uppercase mb-2">时间节点预览</p>
                <div id="timeline-preview" class="space-y-1.5"></div>
              </div>
            </div>
            <label class="toggle-mock inline-flex">
              <input type="checkbox" name="useMock" checked />
              <span>Mock 模式（无需 API Key，适合体验）</span>
            </label>
          </div>

          <div class="flex justify-center pt-4">
            <button type="submit" id="start-btn" class="btn-start text-on-primary px-14 py-4 rounded-full text-lg font-bold flex items-center gap-3">
              <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1">play_arrow</span>
              开始平行推演
            </button>
          </div>
        </form>
      </div>
    </div>

    <aside class="fixed right-0 top-16 h-[calc(100vh-64px)] w-full lg:w-[520px] border-l border-outline-variant bg-surface-container-lowest/95 backdrop-blur-sm flex overflow-hidden shadow-[-4px_0_24px_rgba(0,0,0,0.04)]">
      <div class="w-1/2 h-full p-6 overflow-y-auto no-scrollbar border-r border-outline-variant">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest">环境遥测</h2>
          <span class="text-[10px] font-mono text-outline px-2 py-0.5 bg-surface-container rounded">待机</span>
        </div>
        <div class="space-y-4">
          <div class="telemetry-card">
            <div class="flex justify-between items-center mb-3">
              <span class="text-xs text-on-surface-variant font-medium">不确定性指数</span>
              <span class="material-symbols-outlined text-primary text-lg">blur_on</span>
            </div>
            <div class="text-2xl font-bold text-on-surface">—</div>
            <p class="text-[11px] text-on-surface-variant mt-2">启动推演后实时更新</p>
          </div>
          <div class="telemetry-card">
            <div class="flex justify-between items-center mb-3">
              <span class="text-xs text-on-surface-variant font-medium">路径覆盖度</span>
              <span class="material-symbols-outlined text-secondary text-lg">route</span>
            </div>
            <div class="flex items-end gap-1 h-8 mt-2">
              <div class="mini-bar h-[30%]"></div>
              <div class="mini-bar h-[50%] opacity-80"></div>
              <div class="mini-bar h-[70%] opacity-90"></div>
              <div class="mini-bar h-[40%] opacity-60"></div>
            </div>
          </div>
          <div class="telemetry-card">
            <span class="text-xs text-on-surface-variant font-medium block mb-2">推演准备度</span>
            <div class="h-2 bg-surface-variant rounded-full overflow-hidden">
              <div class="h-full bg-gradient-to-r from-primary to-secondary rounded-full w-0 transition-all duration-500" id="ready-bar"></div>
            </div>
            <p class="text-[10px] font-mono text-outline mt-2 text-right" id="ready-label">填写现状与目标</p>
          </div>
        </div>
      </div>
      <div class="w-1/2 h-full p-6 overflow-y-auto no-scrollbar">
        <h2 class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest mb-6">推演流水线</h2>
        <div class="space-y-5">
          ${PHASE_STEPS.map((s, i) => pipelineStep(s.label, i === 0 ? 'done' : i === 1 ? 'active' : 'pending')).join('')}
        </div>
        <div class="mt-10 p-4 rounded-xl bg-primary-fixed/30 border border-primary-fixed">
          <p class="text-xs text-primary font-bold uppercase mb-1">提示</p>
          <p class="text-[13px] text-on-surface-variant leading-relaxed">现状与目标描述越完整，本体建模与知识图谱越准确，推演结果越可靠。</p>
        </div>
      </div>
    </aside>
  `, { topNav: 'simulate', sidebarActive: 'simulate', mainClass: '' });
}

function pipelineStep(label, state) {
  const dotClass = state === 'done' ? 'pipeline-dot done' : state === 'active' ? 'pipeline-dot active' : 'pipeline-dot';
  const status = state === 'done' ? '已完成' : state === 'active' ? '当前' : '待处理';
  const statusColor = state === 'done' ? 'text-primary' : state === 'active' ? 'text-secondary' : 'text-on-surface-variant';
  return `
    <div class="pipeline-step">
      <div class="${dotClass}"></div>
      <p class="text-sm font-semibold text-on-surface">${label}</p>
      <p class="text-[11px] ${statusColor} font-medium uppercase tracking-wide mt-0.5">${status}</p>
    </div>`;
}

function updateCharCount(textarea, counterId) {
  const el = document.getElementById(counterId);
  if (el && textarea) el.textContent = `${textarea.value.trim().length} 字`;
}

function updateReadyBar() {
  const bg = document.getElementById('background');
  const goal = document.getElementById('goal');
  const bar = document.getElementById('ready-bar');
  const label = document.getElementById('ready-label');
  if (!bg || !goal || !bar) return;
  const bgLen = bg.value.trim().length;
  const goalLen = goal.value.trim().length;
  const pct = Math.min(100, Math.round((Math.min(bgLen, 200) / 200) * 50 + (Math.min(goalLen, 80) / 80) * 50));
  bar.style.width = `${pct}%`;
  if (label) {
    label.textContent = pct >= 80 ? '可以开始推演' : pct >= 40 ? '继续完善描述…' : '填写现状与目标';
  }
}

export function mountSimulate() {
  const form = document.getElementById('sim-form');
  if (!form) return;
  applyPrefsToSimulateForm(form);
  updateTimelinePreview(form);
  const goal = document.getElementById('goal');
  [bg, goal].forEach(el => {
    if (!el) return;
    el.addEventListener('input', () => {
      updateCharCount(el, el.id === 'background' ? 'bg-count' : 'goal-count');
      updateReadyBar();
    });
  });
  updateCharCount(bg, 'bg-count');
  updateCharCount(goal, 'goal-count');
  updateReadyBar();

  const agentRange = document.getElementById('agent-range');
  const periodRange = document.getElementById('period-range');
  agentRange?.addEventListener('input', () => {
    document.getElementById('agent-val').textContent = agentRange.value;
  });
  periodRange?.addEventListener('input', () => {
    document.getElementById('period-val').textContent = periodRange.value;
    updateTimelinePreview(form);
  });

  ['periodTimeUnit', 'periodTimeLength', 'simulationStartDate'].forEach(name => {
    form.querySelector(`[name="${name}"]`)?.addEventListener('input', () => updateTimelinePreview(form));
    form.querySelector(`[name="${name}"]`)?.addEventListener('change', () => updateTimelinePreview(form));
  });
  updateTimelinePreview(form);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('start-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="material-symbols-outlined animate-spin">progress_activity</span> 正在启动…';
    const fd = new FormData(form);
    const bgVal = (fd.get('background') || '').toString().trim();
    const goalVal = (fd.get('goal') || '').toString().trim();
    if (!bgVal || !goalVal) {
      alert('请填写当前现状与最终目标');
      btn.disabled = false;
      btn.innerHTML = '<span class="material-symbols-outlined" style="font-variation-settings: \'FILL\' 1">play_arrow</span> 开始平行推演';
      return;
    }
    const payload = buildPayload(Object.fromEntries(fd.entries()));
    const useMock = fd.get('useMock') === 'on';
    try {
      const { simulation_id } = await API.createSimulation(payload, useMock);
      localStorage.setItem('prds_last_sim', simulation_id);
      location.hash = `#monitor/${simulation_id}`;
    } catch (err) {
      alert('启动失败: ' + err.message);
      btn.disabled = false;
      btn.innerHTML = '<span class="material-symbols-outlined" style="font-variation-settings: \'FILL\' 1">play_arrow</span> 开始平行推演';
    }
  });
}

function updateTimelinePreview(form) {
  const fd = new FormData(form);
  const cfg = timeConfigFrom({
    period_time_unit: fd.get('periodTimeUnit'),
    period_time_length: fd.get('periodTimeLength'),
    simulation_start_date: fd.get('simulationStartDate') || null,
  });
  const periods = Number(fd.get('periods')) || 6;
  const desc = document.getElementById('period-time-desc');
  const preview = document.getElementById('timeline-preview');
  if (desc) {
    desc.textContent = unitLengthLabel(cfg.period_time_unit, cfg.period_time_length);
  }
  if (preview) {
    const items = buildTimelinePreview(cfg, periods);
    preview.innerHTML = items.map(item => `
      <div class="flex items-center gap-2 text-xs bg-surface-container-low rounded-lg px-3 py-2">
        <span class="font-mono font-bold text-primary shrink-0">T${item.period}</span>
        <span class="text-on-surface-variant">${item.label.split(' · ')[0]}</span>
      </div>`).join('');
  }
}
