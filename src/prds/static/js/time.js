export const PERIOD_TIME_UNITS = {
  day: { label: '天', plural: '天' },
  week: { label: '周', plural: '周' },
  month: { label: '月', plural: '月' },
  quarter: { label: '季度', plural: '季度' },
  year: { label: '年', plural: '年' },
};

function parseDate(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function formatIsoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function addMonths(d, months) {
  const day = d.getDate();
  const target = new Date(d.getFullYear(), d.getMonth() + months, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(day, lastDay));
  return target;
}

function addUnit(d, unit, amount) {
  const out = new Date(d);
  if (unit === 'day') {
    out.setDate(out.getDate() + amount);
    return out;
  }
  if (unit === 'week') {
    out.setDate(out.getDate() + amount * 7);
    return out;
  }
  if (unit === 'month') return addMonths(out, amount);
  if (unit === 'quarter') return addMonths(out, amount * 3);
  if (unit === 'year') return addMonths(out, amount * 12);
  return addMonths(out, amount);
}

export function formatPeriodLabel(period, cfg = {}) {
  if (!period || period < 1) return `T${period || 0}`;

  const unit = cfg.period_time_unit || 'month';
  const length = Number(cfg.period_time_length) || 1;
  const startDate = cfg.simulation_start_date || null;
  const meta = PERIOD_TIME_UNITS[unit] || PERIOD_TIME_UNITS.month;

  if (startDate) {
    const start = parseDate(startDate);
    if (start) {
      const offset = (period - 1) * length;
      const rangeStart = addUnit(start, unit, offset);
      const rangeEnd = addUnit(start, unit, offset + length);
      rangeEnd.setDate(rangeEnd.getDate() - 1);
      return `${formatIsoDate(rangeStart)} ~ ${formatIsoDate(rangeEnd)} · T${period}`;
    }
  }

  if (length === 1) return `第${period}${meta.label} · T${period}`;
  const startIdx = (period - 1) * length + 1;
  const endIdx = period * length;
  return `第${startIdx}-${endIdx}${meta.plural} · T${period}`;
}

export function formatPeriodShort(period, cfg = {}) {
  const full = formatPeriodLabel(period, cfg);
  return full.split(' · ')[0] || full;
}

export function buildTimelinePreview(cfg, periods) {
  const count = Math.min(Number(periods) || 0, 6);
  const items = [];
  for (let p = 1; p <= count; p += 1) {
    items.push({ period: p, label: formatPeriodLabel(p, cfg) });
  }
  return items;
}

export function timeConfigFrom(source = {}) {
  return {
    period_time_unit: source.period_time_unit || 'month',
    period_time_length: Number(source.period_time_length) || 1,
    simulation_start_date: source.simulation_start_date || null,
  };
}

export function unitLengthLabel(unit, length) {
  const meta = PERIOD_TIME_UNITS[unit] || PERIOD_TIME_UNITS.month;
  if (length === 1) return `每周期 1 ${meta.label}`;
  return `每周期 ${length} ${meta.plural}`;
}
