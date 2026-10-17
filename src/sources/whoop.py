"""WHOOP adapter: stored WHOOP rows (src/ingestion/whoop_mappers.py, or read back from the
database) -> device-agnostic DailyRecords. Pure logic, no I/O."""
from datetime import date, datetime, timedelta, timezone

from src.analysis.records import DailyRecord

SOURCE = "whoop"
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


def sleep_need_minutes(raw: dict | None) -> tuple[float | None, float | None]:
    """WHOOP's sleep need from a raw sleep payload: (baseline, total) in minutes.

    total = baseline + need from sleep debt + need from recent strain + nap credit (negative).
    Returns (None, None) when the payload has no sleep_needed block.
    """
    need = ((raw or {}).get("score") or {}).get("sleep_needed") or {}
    base = need.get("baseline_milli")
    if base is None:
        return None, None
    extra = sum(need.get(k) or 0 for k in ("need_from_sleep_debt_milli", "need_from_recent_strain_milli"))
    total = base + extra + (need.get("need_from_recent_nap_milli") or 0)
    return round(base / 60_000, 1), round(total / 60_000, 1)


def daily_records(sleeps: list[dict], recoveries: list[dict], cycles: list[dict]) -> list[DailyRecord]:
    """One record per behavior day that has a main sleep and/or a scored cycle."""
    # Main (non-nap) scored sleep per day; if several, keep the longest time in bed.
    main: dict[date, dict] = {}
    for s in sleeps:
        if s.get("nap") or not _scored(s) or s.get("start") is None:
            continue
        d = sleep_day(s)
        if d not in main or (s.get("in_bed_min") or 0) > (main[d].get("in_bed_min") or 0):
            main[d] = s

    rec = {str(r["sleep_id"]): r for r in recoveries if r.get("sleep_id") and _scored(r)}
    load: dict[date, float] = {}
    for c in sorted(cycles, key=lambda c: c["start"]):
        if _scored(c) and c.get("strain") is not None:
            load[cycle_day(c)] = c["strain"]

    records = []
    for d in sorted(set(main) | set(load)):
        r = DailyRecord(day=d, source=SOURCE, load=load.get(d))
        s = main.get(d)
        if s is not None:
            stages = [s.get("light_min"), s.get("deep_min"), s.get("rem_min")]
            offset = parse_offset(s.get("timezone_offset"))
            r.total_sleep_min = sum(stages) if all(v is not None for v in stages) else None
            r.deep_min, r.rem_min, r.in_bed_min = s.get("deep_min"), s.get("rem_min"), s.get("in_bed_min")
            r.sleep_efficiency_pct = s.get("sleep_efficiency_pct")
            r.sleep_performance_pct = s.get("sleep_performance_pct")
            r.respiratory_rate = s.get("respiratory_rate")
            r.sleep_start_local = _local(s["start"], offset)
            r.sleep_need_baseline_min, r.sleep_need_total_min = sleep_need_minutes(s.get("raw"))
            r.tz_offset_min = offset
            r.source_sleep_id = str(s["id"])
            m = rec.get(str(s["id"]), {})
            r.recovery_score = m.get("recovery_score")
            r.hrv_rmssd_milli = m.get("hrv_rmssd_milli")
            r.resting_heart_rate = m.get("resting_heart_rate")
            r.calibrating = m.get("user_calibrating")
        records.append(r)
    return records
