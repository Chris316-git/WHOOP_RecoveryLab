"""Assemble one row per behavior day from device-agnostic records and calendar features.
Pure logic, no I/O.

Day alignment: day `d` is the day the behavior happens (e.g. coffee at 4pm on d). Its
outcomes are the main sleep that starts on the evening of d and the readiness scored when
waking up on d+1. Covariates are the load accumulated on d and the calendar load of d,
both of which precede that sleep.

Wearable-specific parsing lives in src/sources/ (e.g. src/sources/whoop.py).
"""
import pandas as pd

from src.analysis.records import NUMERIC_FIELDS, RECORD_FIELDS, DailyRecord

PANEL_METRICS = [
    "recovery_score", "hrv_rmssd_milli", "resting_heart_rate", "respiratory_rate",
    "sleep_performance_pct", "sleep_efficiency_pct", "total_sleep_min", "deep_min", "rem_min",
]
CALENDAR_COLUMNS = ["event_count", "busy_minutes", "meeting_minutes",
                    "longest_free_block_min", "back_to_back_count"]


def build_panel(records: list[DailyRecord], calendar: list[dict] | None = None) -> pd.DataFrame:
    """DataFrame indexed by behavior day, one row per day (the last record wins on duplicates)."""
    if not records:
        return pd.DataFrame(columns=["day", *RECORD_FIELDS[1:]]).set_index("day")
    panel = pd.DataFrame([r.to_dict() for r in records]).drop_duplicates("day", keep="last")
    panel = panel.set_index("day").sort_index()
    panel[NUMERIC_FIELDS] = panel[NUMERIC_FIELDS].apply(pd.to_numeric, errors="coerce")

    cal = {r["day"]: r for r in (calendar or [])}
    for col in CALENDAR_COLUMNS:
        panel[col] = pd.to_numeric(pd.Series([cal.get(d, {}).get(col) for d in panel.index],
                                             index=panel.index), errors="coerce")
    panel["has_calendar"] = [d in cal for d in panel.index]
    panel["dow"] = [d.weekday() for d in panel.index]  # Monday = 0
    panel.index.name = "day"
    return panel
