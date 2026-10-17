"""Build the daily summary from the daily panel and today's calendar. Pure logic, no I/O.

Every number in the report is computed here. The day's focus (src/planner/focus.py) is
chosen by transparent rules from these numbers; it is NOT a causal finding. Causal claims
come only from completed experiments.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.planner.focus import choose_focus
from src.report.signals import compute_signals

BASELINE_DAYS = 30
MIN_BASELINE_NIGHTS = 7
ACTIVE_START, ACTIVE_END = time(8, 0), time(20, 0)
MIN_FREE_WINDOW_MIN = 30


@dataclass(frozen=True)
class ShownMetric:
    key: str
    label: str
    unit: str
    higher_is_better: bool
    digits: int = 0


SHOWN = [
    ShownMetric("recovery_score", "Recovery", "%", True),
    ShownMetric("hrv_rmssd_milli", "HRV", "ms", True, 1),
    ShownMetric("resting_heart_rate", "Resting heart rate", "bpm", False),
    ShownMetric("sleep_performance_pct", "Sleep performance", "%", True),
    ShownMetric("total_sleep_min", "Total sleep", "min", True),
    ShownMetric("deep_min", "Deep sleep", "min", True),
    ShownMetric("rem_min", "REM sleep", "min", True),
]


def recovery_zone(score: float | None) -> str | None:
    """WHOOP's own zones: green 67-100, yellow 34-66, red 0-33."""
    if score is None or pd.isna(score):
        return None
    return "green" if score >= 67 else "yellow" if score >= 34 else "red"


def _metric_summary(m: ShownMetric, value, history: pd.Series) -> dict:
    history = pd.to_numeric(history, errors="coerce").dropna()
    out = dict(key=m.key, label=m.label, unit=m.unit, value=None, baseline_median=None,
               delta=None, percentile=None, status="no_data", baseline_nights=int(len(history)))
    if value is None or pd.isna(value):
        return out
    out["value"] = round(float(value), m.digits)
    if len(history) < MIN_BASELINE_NIGHTS:
        out["status"] = "no_baseline"
        return out
    median = float(history.median())
    pct = float((history < value).mean() + 0.5 * (history == value).mean())  # mid-rank percentile
    out.update(baseline_median=round(median, m.digits), delta=round(float(value) - median, m.digits),
               percentile=round(100 * pct))
    better = pct if m.higher_is_better else 1 - pct
    out["status"] = "better" if better >= 0.8 else "worse" if better <= 0.2 else "typical"
    return out


def free_windows(events: list[dict], day: date, tz: str, now: datetime | None = None,
                 min_minutes: int = MIN_FREE_WINDOW_MIN) -> list[dict]:
    """Gaps between busy blocks within 08:00-20:00 local time (from `now` onward if given)."""
    zone = ZoneInfo(tz)
    win_start = datetime.combine(day, ACTIVE_START, zone)
    win_end = datetime.combine(day, ACTIVE_END, zone)
    if now is not None:
        win_start = max(win_start, now.astimezone(zone))
    busy = sorted((max(e["start"], win_start), min(e["end"], win_end)) for e in events)
    windows, cursor = [], win_start
    for s, e in busy:
        if e <= s:
            continue
        if (s - cursor).total_seconds() >= min_minutes * 60:
            windows.append((cursor, s))
        cursor = max(cursor, e)
    if (win_end - cursor).total_seconds() >= min_minutes * 60:
        windows.append((cursor, win_end))
    return [dict(start=s.astimezone(zone).strftime("%H:%M"), end=e.astimezone(zone).strftime("%H:%M"),
                 minutes=int((e - s).total_seconds() // 60)) for s, e in windows]


def calendar_summary(events: list[dict], day: date, tz: str, now: datetime | None = None) -> dict:
    zone = ZoneInfo(tz)
    day_start = datetime.combine(day, time.min, zone)
    day_end = day_start + timedelta(days=1)
    spans = sorted((max(e["start"], day_start), min(e["end"], day_end)) for e in events)
    merged: list[list[datetime]] = []
    for s, e in spans:
        if e <= s:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    busy_min = sum((e - s).total_seconds() / 60 for s, e in merged)
    windows = free_windows(events, day, tz, now)

    # Busy/free segments across the active window (08:00-20:00), for the email timeline.
    win_start = datetime.combine(day, ACTIVE_START, zone)
    win_end = datetime.combine(day, ACTIVE_END, zone)
    timeline, cursor = [], win_start
    for s, e in merged:
        s, e = max(s, win_start), min(e, win_end)
        if e <= s:
            continue
        if s > cursor:
            timeline.append(("free", cursor, s))
        timeline.append(("busy", s, e))
        cursor = max(cursor, e)
    if cursor < win_end:
        timeline.append(("free", cursor, win_end))
    total = (win_end - win_start).total_seconds()
    timeline = [dict(kind=k, start=a.astimezone(zone).strftime("%H:%M"), end=b.astimezone(zone).strftime("%H:%M"),
                     share=round((b - a).total_seconds() / total, 4)) for k, a, b in timeline]
    now_share = None
    if now is not None and win_start <= now.astimezone(zone) <= win_end:
        now_share = round((now.astimezone(zone) - win_start).total_seconds() / total, 4)
    return dict(
        event_count=len(spans),
        meeting_count=sum(1 for e in events if e.get("attendee_count", 0) >= 2),
        busy_hours=round(busy_min / 60, 1),
        first_start=merged[0][0].astimezone(zone).strftime("%H:%M") if merged else None,
        last_end=merged[-1][1].astimezone(zone).strftime("%H:%M") if merged else None,
        free_windows=windows,
        longest_free=max(windows, key=lambda w: w["minutes"]) if windows else None,
        timeline=timeline,
        now_share=now_share,
    )


def build_daily_summary(panel: pd.DataFrame, today: date, tz: str,
                        events_today: list[dict] | None = None, now: datetime | None = None,
                        recent_focuses: list[str] | None = None, not_useful: set[str] | None = None) -> dict:
    """Summary for the morning of `today`: last night's sleep and recovery vs. your own
    30-day baseline, the last 7 days vs. that baseline, and today's calendar."""
    last_night = today - timedelta(days=1)  # behavior day whose sleep ended this morning
    hist_lo = last_night - timedelta(days=BASELINE_DAYS)
    hist = panel[(panel.index >= hist_lo) & (panel.index < last_night)] if len(panel) else panel
    row = panel.loc[last_night] if last_night in panel.index else None

    metrics = [_metric_summary(m, None if row is None else row.get(m.key),
                               hist[m.key] if m.key in hist else pd.Series(dtype=float)) for m in SHOWN]
    recovery = metrics[0]["value"]

    week_lo = today - timedelta(days=7)
    week = panel[(panel.index >= week_lo) & (panel.index < today)] if len(panel) else panel
    trend = {}
    for key in ("recovery_score", "hrv_rmssd_milli"):
        enough_week = key in week and week[key].notna().sum() >= 3
        enough_hist = key in hist and hist[key].notna().sum() >= MIN_BASELINE_NIGHTS
        if enough_week and enough_hist:
            trend[key] = dict(week_mean=round(float(week[key].mean()), 1),
                              baseline_median=round(float(hist[key].median()), 1))

    load = None if row is None else row.get("load")
    summary = dict(
        date=today.isoformat(),
        weekday=today.strftime("%A"),
        timezone=tz,
        last_night_scored=row is not None and pd.notna(row.get("recovery_score")),
        recovery_zone=recovery_zone(recovery),
        metrics=metrics,
        yesterday_load=None if load is None or pd.isna(load) else round(float(load), 1),
        week_trend=trend,
        calendar=calendar_summary(events_today, today, tz, now) if events_today is not None else None,
        signals=compute_signals(panel, today),
    )
    summary["focus"] = choose_focus(summary, panel, today, now, recent_focuses, not_useful)
    return summary
