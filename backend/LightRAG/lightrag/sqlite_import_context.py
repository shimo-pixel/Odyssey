"""Helpers for SQLite-import documents (table labels, file-path parsing)."""

from __future__ import annotations

import re
from pathlib import Path

_SQLITE_TABLE_FILE_RE = re.compile(
    r"sqlite_[^_]+_([A-Za-z][A-Za-z0-9_]*)\.txt$",
    re.IGNORECASE,
)

_TABLE_DISPLAY_LABELS: dict[str, str] = {
    "training_task": "训练任务主表",
    "training_participant_group": "参训人员编组表",
    "training_attendance_log": "训练考勤流水表",
    "flight_plan_detail": "飞行计划明细表",
    "flight_execution_record": "飞行实施记录表",
    "training_score_record": "训练成绩表",
    "equipment_fault_record": "装备故障记录表",
    "material_consumption_log": "物资消耗流水表",
    "material_settlement_summary": "物资决算汇总表",
    "pilot": "飞行员表",
    "flight_mission": "飞行任务表",
    "flight_training": "飞行训练表",
    "aircraft": "飞机表",
    "military_unit": "军事单位表",
    "weapon_inventory": "武器库存表",
}


def table_display_label(table: str) -> str:
    return _TABLE_DISPLAY_LABELS.get(table, f"{table}表")


def format_reference_label(file_path: str) -> str:
    """Human-readable citation label for query references."""
    parsed = parse_sqlite_table_from_file_path(file_path)
    if parsed is not None:
        _table, table_label = parsed
        return f"表 {table_label}"

    basename = Path(str(file_path).replace("\\", "/")).name
    if basename:
        return basename
    return str(file_path)


def parse_sqlite_table_from_file_path(file_path: str) -> tuple[str, str] | None:
    """Return (sqlite_table_name, chinese_table_label) for sqlite import docs."""
    if not file_path:
        return None

    basename = Path(str(file_path).replace("\\", "/")).name
    if not basename.startswith("sqlite_") or not basename.endswith(".txt"):
        return None
    if basename.endswith("_entity_registry.txt"):
        return None

    match = _SQLITE_TABLE_FILE_RE.match(basename)
    if not match:
        return None

    table = match.group(1)
    return table, table_display_label(table)
