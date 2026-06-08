import { t, unitLabel, unitPlural } from './i18n.js';

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
  const label = unitLabel(unit);
  const plural = unitPlural(unit);

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

  if (length === 1) {
    return `${t('unit.periodNth', { n: period, unit: label })} · T${period}`;
  }
  const startIdx = (period - 1) * length + 1;
  const endIdx = period * length;
  return `${t('unit.periodRange', { start: startIdx, end: endIdx, unit: plural })} · T${period}`;
}

export function formatPeriodShort(period, cfg = {}) {
  const full = formatPeriodLabel(period, cfg);
  return full.split(' · ')[0] || full;
}

export function buildTimelinePreview(cfg, periods, maxItems = 8) {
  const total = Math.max(0, Number(periods) || 0);
  const items = [];
  if (total <= maxItems) {
    for (let p = 1; p <= total; p += 1) {
      items.push({ period: p, label: formatPeriodLabel(p, cfg) });
    }
    return items;
  }
  // Condense long horizons: show the first periods, a gap marker, then the final period.
  const head = maxItems - 2;
  for (let p = 1; p <= head; p += 1) {
    items.push({ period: p, label: formatPeriodLabel(p, cfg) });
  }
  items.push({ gap: true, hidden: total - head - 1 });
  items.push({ period: total, label: formatPeriodLabel(total, cfg) });
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
  const u = length === 1 ? unitLabel(unit) : unitPlural(unit);
  return t('unit.perPeriod', { n: length, unit: u });
}
