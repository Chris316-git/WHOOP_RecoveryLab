"""Assemble one row per behavior day from WHOOP and calendar rows. Pure logic, no I/O.

Day alignment: day `d` is the day the behavior happens (e.g. coffee at 4pm on d).
Its outcomes are the main sleep that starts on the evening of d and the recovery
scored when waking up on d+1. Covariates are the strain accumulated on d and the
calendar load of d, both of which precede that sleep.

Inputs are lists of row dicts as produced by `src.ingestion.whoop_mappers` (or read
back from the database), so the same code serves live and synthetic data.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd

PANEL_METRICS = [
    "recovery_score", "hrv_rmssd_milli", "resting_heart_rate", "respiratory_rate",
    "sleep_performance_pct", "sleep_efficiency_pct", "total_sleep_min", "deep_min", "rem_min",
]
CALENDAR_COLUMNS = ["event_count", "busy_minutes", "meeting_minutes",
                    "longest_free_block_min", "back_to_back_count"]
SLEEP_DAY_SHIFT = timedelta(hours=12)  # a sleep starting before noon belongs to the previous day


def parse_offset(value: str | None) -> int | None:
    """WHOOP timezone_offset like "-07:00" -> minutes east of UTC."""
    if not value:
        return None
    sign = -1 if value.startswith("-") else 1
    hours, minutes = value.lstrip("+-").split(":")
    return sign * (int(hours) * 60 + int(minutes))


def _local(dt: datetime, offset_min: int | None) -> datetime:
    if dt.tzinfo is None:  # SQLite drops tzinfo; values are stored in UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(minutes=offset_min or 0)


def _scored(row: dict) -> bool:
    return row.get("score_state") in (None, "SCORED")


def sleep_day(row: dict) -> date:
    return (_local(row["start"], parse_offset(row.get("timezone_offset"))) - SLEEP_DAY_SHIFT).date()


def cycle_day(row: dict) -> date:
    """A cycle's day is the local date of its midpoint, which is robust to whether a
    cycle is counted from sleep onset or from waking up."""
    offset = parse_offset(row.get("timezone_offset"))
    start = _local(row["start"], offset)
    end = _local(row["end"], offset) if row.get("end") else start + timedelta(hours=24)
    return (start + (end - start) / 2).date()


def build_panel(
    sleeps: list[dict],
    recoveries: list[dict],
    cycles: list[dict],
    calendar: list[dict] | None = None,
) -> pd.DataFrame:
    """DataFrame indexed by behavior day with outcome metrics and covariates."""
    # Main (non-nap) scored sleep per behavior day; if several, keep the longest.
    sleep_rows = []
    for s in sleeps:
        if s.get("nap") or not _scored(s) or s.get("start") is None:
            continue
        stages = [s.get("light_min"), s.get("deep_min"), s.get("rem_min")]
        sleep_rows.append(dict(
            day=sleep_day(s),
            sleep_id=str(s["id"]),
            in_bed_min=s.get("in_bed_min") or 0.0,
            total_sleep_min=sum(stages) if all(v is not None for v in stages) else None,
            deep_min=s.get("deep_min"),
            rem_min=s.get("rem_min"),
            sleep_performance_pct=s.get("sleep_performance_pct"),
            sleep_efficiency_pct=s.get("sleep_efficiency_pct"),
            respiratory_rate=s.get("respiratory_rate"),
            tz_offset_min=parse_offset(s.get("timezone_offset")),
        ))
    if not sleep_rows:
        return pd.DataFrame(columns=["day", *PANEL_METRICS]).set_index("day")
    panel = (pd.DataFrame(sleep_rows).sort_values("in_bed_min")
             .groupby("day").tail(1).set_index("day").sort_index())

    rec = {str(r["sleep_id"]): r for r in recoveries if r.get("sleep_id") and _scored(r)}
    for col in ("recovery_score", "hrv_rmssd_milli", "resting_heart_rate"):
        panel[col] = [rec.get(sid, {}).get(col) for sid in panel["sleep_id"]]
    panel["user_calibrating"] = [rec.get(sid, {}).get("user_calibrating") for sid in panel["sleep_id"]]

    strain = {}
    for c in sorted(cycles, key=lambda c: c["start"]):
        if _scored(c) and c.get("strain") is not None:
            strain[cycle_day(c)] = c["strain"]
    panel["strain"] = [strain.get(d) for d in panel.index]

    cal = {r["day"]: r for r in (calendar or [])}
    for col in CALENDAR_COLUMNS:
        panel[col] = [cal.get(d, {}).get(col) for d in panel.index]
    panel["has_calendar"] = [d in cal for d in panel.index]

    panel["dow"] = [d.weekday() for d in panel.index]  # Monday = 0
    panel.index.name = "day"
    numeric = [*PANEL_METRICS, "strain", *CALENDAR_COLUMNS, "tz_offset_min"]
    panel[numeric] = panel[numeric].apply(pd.to_numeric, errors="coerce")
    return panel
