import calendar
from datetime import date, datetime, timedelta


_UNIT_ZH = {
    "day": "天",
    "week": "周",
    "month": "月",
    "quarter": "季度",
    "year": "年",
}


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_unit(d: date, unit: str, amount: int) -> date:
    if unit == "day":
        return d + timedelta(days=amount)
    if unit == "week":
        return d + timedelta(weeks=amount)
    if unit == "month":
        return _add_months(d, amount)
    if unit == "quarter":
        return _add_months(d, amount * 3)
    if unit == "year":
        return _add_months(d, amount * 12)
    return _add_months(d, amount)


def compute_period_label(
    period: int,
    *,
    unit: str = "month",
    length: int = 1,
    start_date: str | None = None,
) -> str:
    if period < 1:
        return f"T{period}"

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            offset = (period - 1) * length
            range_start = _add_unit(start, unit, offset)
            range_end = _add_unit(start, unit, offset + length) - timedelta(days=1)
            return f"{range_start.isoformat()} ~ {range_end.isoformat()} · T{period}"
        except ValueError:
            pass

    unit_label = _UNIT_ZH.get(unit, "月")
    if length == 1:
        return f"第{period}{unit_label} · T{period}"
    start_idx = (period - 1) * length + 1
    end_idx = period * length
    return f"第{start_idx}-{end_idx}{unit_label} · T{period}"


def time_config_dict(
    *,
    unit: str = "month",
    length: int = 1,
    start_date: str | None = None,
) -> dict:
    return {
        "period_time_unit": unit,
        "period_time_length": length,
        "simulation_start_date": start_date,
    }
