"""The coach agent's tools: read-only views of the user's data, plus proposing a calendar block.

Every number the agent may use comes from these functions, computed in Python. The agent
decides which tools to call and in what order; it never sees raw records, event titles,
names or email addresses. Nothing is written here: a proposed block goes on the calendar
only when the user taps "Add to calendar" (see src/coach/service.py).

The pure functions take data frames and lists, so they are tested without a database;
`CoachData` loads that data for one user.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from src.planner.habits import normalize
from src.reasoning.validate import HARD_WORDS

HARD_STRAIN = 14.0
MAX_DAYS = 60
MIN_GROUP = 3   # fewer days than this in a group: report the counts, no comparison
EVENING_START = 20 * 60   # a wind-down may start from here, inside or outside free time

# metric -> (panel column, label, unit, when it is measured)
METRICS = {
    "recovery": ("recovery_score", "Recovery", "%", "morning"),
    "hrv": ("hrv_rmssd_milli", "HRV", "ms", "morning"),
    "resting_hr": ("resting_heart_rate", "Resting heart rate", "bpm", "morning"),
    "sleep_hours": ("total_sleep_min", "Sleep", "hours", "morning"),
    "sleep_performance": ("sleep_performance_pct", "Sleep performance", "%", "morning"),
    "strain": ("load", "Day strain", "", "day"),
    "bedtime": ("sleep_start_local", "Bedtime", "clock", "night"),
}
SPLITS = ("after_hard_days", "after_activity", "weekend_nights")


def _clock(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _bed_minutes(ts) -> float | None:
    """Bedtime as minutes after noon-to-noon, so 23:30 and 00:30 average sensibly."""
    if ts is None or pd.isna(ts):
        return None
    t = pd.Timestamp(ts)
    m = t.hour * 60 + t.minute
    return m + 1440 if m < 12 * 60 else m


def _values(panel: pd.DataFrame, metric: str) -> pd.Series:
    """Values indexed by the date they belong to: the morning for sleep and recovery metrics
    (panel row d holds the night after d), the day itself for strain, the night for bedtime."""
    col, _, _, when = METRICS[metric]
    if col not in panel:
        return pd.Series(dtype=float)
    s = panel[col]
    if metric == "bedtime":
        s = s.map(_bed_minutes)
    s = pd.to_numeric(s, errors="coerce")
    if metric == "sleep_hours":
        s = s / 60
    if when == "morning":
        s.index = [d + timedelta(days=1) for d in s.index]
    return s.dropna()


def _fmt(metric: str, v: float) -> str | float:
    if metric == "bedtime":
        return _clock(v)
    return round(float(v), 1)


def metric_history(panel: pd.DataFrame, metric: str, days: int, today: date) -> dict:
    if metric not in METRICS:
        return dict(error=f"unknown metric; use one of {sorted(METRICS)}")
    days = max(3, min(MAX_DAYS, int(days)))
    s = _values(panel, metric)
    s = s[[today - timedelta(days=days) < d <= today for d in s.index]]
    _, label, unit, when = METRICS[metric]
    if s.empty:
        return dict(metric=label, values=[], note="no data in this period")
    out = dict(metric=label, unit="" if unit == "clock" else unit,
               dated_by={"morning": "the morning it was measured", "day": "the day", "night": "the night"}[when],
               values=[dict(date=d.isoformat(), value=_fmt(metric, v)) for d, v in s.items()],
               days_with_data=len(s), average=_fmt(metric, s.mean()), median=_fmt(metric, s.median()))
    if metric != "bedtime":
        out.update(lowest=_fmt(metric, s.min()), highest=_fmt(metric, s.max()))
    return out


def _activity_days(workouts: list[dict], sport: str) -> set[date]:
    from src.sources.whoop import _local, parse_offset
    want = normalize(sport)
    return {_local(w["start"], parse_offset(w.get("timezone_offset"))).date()
            for w in workouts if want and want in normalize(w.get("sport_name"))}


def compare(panel: pd.DataFrame, workouts: list[dict], metric: str, split: str, today: date,
            sport: str | None = None, days: int = MAX_DAYS) -> dict:
    """The night after (and next morning of) two groups of days. Association only."""
    if metric not in METRICS or metric == "strain":
        return dict(error="metric must be one of recovery, hrv, resting_hr, sleep_hours, sleep_performance, bedtime")
    if split not in SPLITS:
        return dict(error=f"split must be one of {list(SPLITS)}")
    lo = today - timedelta(days=days)
    s = _values(panel, metric)
    # re-key everything by the behavior day d (the day before the night it describes)
    if METRICS[metric][3] == "morning":
        s.index = [d - timedelta(days=1) for d in s.index]
    s = s[[lo <= d < today for d in s.index]]
    if split == "after_hard_days":
        load = pd.to_numeric(panel.get("load", pd.Series(dtype=float)), errors="coerce")
        hard = {d for d, v in load.items() if v >= HARD_STRAIN}
        groups = (f"after days with strain {HARD_STRAIN:g} or more", "after other days")
        in_a = lambda d: d in hard  # noqa: E731
    elif split == "after_activity":
        if not sport:
            return dict(error="give the activity, e.g. sport='golf'")
        days_with = _activity_days(workouts, sport)
        groups = (f"after days with {normalize(sport)}", f"after days without {normalize(sport)}")
        in_a = lambda d: d in days_with  # noqa: E731
    else:
        groups = ("Friday and Saturday nights", "other nights")
        in_a = lambda d: d.weekday() in (4, 5)  # noqa: E731
    a = s[[in_a(d) for d in s.index]]
    b = s[[not in_a(d) for d in s.index]]
    _, label, unit, _ = METRICS[metric]
    out = dict(metric=label, unit="" if unit == "clock" else unit, period_days=days,
               group_a=dict(name=groups[0], days=len(a)), group_b=dict(name=groups[1], days=len(b)),
               note="Association in your own data, not proof of cause; other things differ between these days.")
    if len(a) < MIN_GROUP or len(b) < MIN_GROUP:
        out["result"] = f"not enough days to compare (need at least {MIN_GROUP} in each group)"
        return out
    out["group_a"]["average"] = _fmt(metric, a.mean())
    out["group_b"]["average"] = _fmt(metric, b.mean())
    diff = a.mean() - b.mean()
    out["difference"] = (f"{abs(round(diff)):g} min {'later' if diff > 0 else 'earlier'}" if metric == "bedtime"
                         else round(float(diff), 1))
    return out


def free_time(events: list[dict], day: date, tz: str, now: datetime | None) -> dict:
    from src.report.daily import free_windows
    start_from = now if now is not None and now.date() == day else None
    windows = free_windows(events, day, tz, start_from)
    return dict(date=day.isoformat(), free_windows=windows,
                note="Free gaps between calendar events, 07:00-24:00 local time, from now on for today.")


_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
KINDS = ("easy", "hard", "wind_down", "other")


def check_block(day: date, start: str, minutes, title: str, kind: str, windows: list[dict],
                now: datetime | None, hard_allowed: bool) -> list[str]:
    """Problems with a proposed block (empty = fine)."""
    problems = []
    if kind not in KINDS:
        problems.append(f"kind must be one of {list(KINDS)}")
    if not isinstance(start, str) or not _HHMM.match(start.strip()):
        return problems + ["start must be HH:MM, 24-hour"]
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return problems + ["minutes must be a number"]
    if not 10 <= minutes <= 180:
        problems.append("minutes must be between 10 and 180")
    if not title or len(title) > 70:
        problems.append("title must be 1-70 characters")
    s = _to_min(start)
    e = s + minutes
    if now is not None and now.date() == day and s < now.hour * 60 + now.minute:
        problems.append("start is in the past")
    hard = kind == "hard" or any(w in (title or "").lower() for w in HARD_WORDS)
    if hard and not hard_allowed:
        problems.append("today's data argues against a hard session (see get_today, safety)")
    if kind == "wind_down":
        if s < EVENING_START:
            problems.append("a wind-down starts in the evening (20:00 or later)")
    elif not any(_to_min(w["start"]) <= s and e <= _to_min(w["end"]) for w in windows):
        problems.append("not inside a free window; call get_free_time and pick a time inside one")
    return problems


def plans_view(plans: list[dict]) -> list[dict]:
    """Past suggestions as the agent sees them: what was suggested, the response, the measured
    outcome, and the agent's own notes for the next day."""
    out = []
    for p in sorted(plans, key=lambda p: p["day"], reverse=True):
        block = p.get("final_block") or p.get("block")
        out.append(dict(day=p["day"], suggested=p.get("title") or p.get("focus"),
                        block=f"{block['start']}-{block['end']} {block['title']}" if block else None,
                        response=p.get("response") or "no response", calendar=p.get("calendar_status"),
                        outcome=p.get("outcome"), outcome_detail=p.get("outcome_detail"),
                        agent_notes=p.get("agent_notes")))
    return out


@dataclass
class CoachData:
    """Loads one user's data for the tools (read-only)."""
    session_factory: object
    user_id: int
    tz: str
    now: datetime

    def panel(self) -> pd.DataFrame:
        from src.report.data import load_recent_panel
        with self.session_factory() as session:
            return load_recent_panel(session, self.user_id, self.now.date())

    def workouts(self) -> list[dict]:
        from src.report.data import load_recent_workouts
        with self.session_factory() as session:
            return load_recent_workouts(session, self.user_id, self.now.date(), days=MAX_DAYS)

    def events(self, day: date) -> list[dict]:
        from src.report.data import load_events_for_day
        with self.session_factory() as session:
            return load_events_for_day(session, self.user_id, day, self.tz)

    def memories(self) -> list[dict]:
        from src.memory import store
        with self.session_factory() as session:
            return store.active(session, self.user_id)

    def save_memory(self, kind: str, text: str) -> dict | None:
        from src.memory import store
        with self.session_factory() as session:
            return store.add(session, self.user_id, kind, text)

    def recent_plans(self, days: int) -> list[dict]:
        from src.report.data import load_recent_plans
        with self.session_factory() as session:
            return load_recent_plans(session, self.user_id, self.now.date() + timedelta(days=1), days=days + 1)

    def latest_case(self) -> tuple[str, dict] | None:
        """This morning's case file (the numbered evidence behind today's email), or yesterday's."""
        from src.db.models import DailyPlan
        with self.session_factory() as session:
            for k in (0, 1):
                day = self.now.date() - timedelta(days=k)
                p = session.get(DailyPlan, (self.user_id, day))
                if p is not None and p.evidence:
                    return day.isoformat(), dict(p.evidence, today_focus=p.title or p.focus)
        return None
