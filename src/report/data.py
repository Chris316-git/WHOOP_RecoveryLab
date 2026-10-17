"""Load what the daily report needs from the database."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.panel import build_panel
from src.db.models import (
    CalendarEvent,
    Cycle,
    DailyCalendarFeatures,
    DailyPlan,
    Recovery,
    Sleep,
    Workout,
)
from src.sources import whoop

HISTORY_DAYS = 70  # enough for 30-day baselines before the last week and 8 weeks of weekday patterns


def _as_dict(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


def load_recent_panel(session: Session, user_id: int, today: date) -> pd.DataFrame:
    lo = datetime.combine(today - timedelta(days=HISTORY_DAYS), time.min, timezone.utc)
    sleeps = [_as_dict(s) for s in session.scalars(
        select(Sleep).where(Sleep.user_id == user_id, Sleep.start >= lo))]
    ids = [s["id"] for s in sleeps]
    recoveries = [_as_dict(r) for r in session.scalars(
        select(Recovery).where(Recovery.user_id == user_id, Recovery.sleep_id.in_(ids)))] if ids else []
    cycles = [_as_dict(c) for c in session.scalars(
        select(Cycle).where(Cycle.user_id == user_id, Cycle.start >= lo - timedelta(days=1)))]
    calendar = [_as_dict(c) for c in session.scalars(
        select(DailyCalendarFeatures).where(DailyCalendarFeatures.user_id == user_id,
                                            DailyCalendarFeatures.day >= lo.date()))]
    return build_panel(whoop.daily_records(sleeps, recoveries, cycles), calendar)


def load_events_for_day(session: Session, user_id: int, day: date, tz: str) -> list[dict]:
    """Timed busy events overlapping the local day (time blocks only; no titles exist)."""
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time.min, zone)
    end = start + timedelta(days=1)
    rows = session.scalars(select(CalendarEvent).where(
        CalendarEvent.user_id == user_id, CalendarEvent.start < end, CalendarEvent.end > start,
        CalendarEvent.all_day.is_(False), CalendarEvent.is_busy.is_(True)))
    return [dict(start=r.start, end=r.end, attendee_count=r.attendee_count) for r in rows]


def load_recent_focuses(session: Session, user_id: int, today: date, days: int = 3) -> list[str]:
    """Focuses chosen on the previous `days` days, most recent first (missing days end the run)."""
    rows = {r.day: r.focus for r in session.scalars(select(DailyPlan).where(
        DailyPlan.user_id == user_id, DailyPlan.day >= today - timedelta(days=days), DailyPlan.day < today))}
    out = []
    for k in range(1, days + 1):
        d = today - timedelta(days=k)
        if d not in rows:
            break
        out.append(rows[d])
    return out


NOT_USEFUL_DAYS = 14


def load_not_useful(session: Session, user_id: int, today: date, days: int = NOT_USEFUL_DAYS) -> set[str]:
    """Focuses the user marked "not useful" in the last `days` days."""
    return set(session.scalars(select(DailyPlan.focus).where(
        DailyPlan.user_id == user_id, DailyPlan.day >= today - timedelta(days=days), DailyPlan.day < today,
        DailyPlan.response == "not_useful")))


def load_plan(session: Session, user_id: int, day: date) -> dict | None:
    p = session.get(DailyPlan, (user_id, day))
    if p is None:
        return None
    return dict(focus=p.focus, block=p.block, final_block=p.final_block, response=p.response,
                calendar_status=p.calendar_status, outcome=p.outcome)


def load_recent_workouts(session: Session, user_id: int, today: date, days: int = 56) -> list[dict]:
    """Workouts of the last `days` days: activity name, times and strain only."""
    lo = datetime.combine(today - timedelta(days=days), time.min, timezone.utc)
    rows = session.scalars(select(Workout).where(Workout.user_id == user_id, Workout.start >= lo))
    return [dict(sport_name=w.sport_name, start=w.start, end=w.end, timezone_offset=w.timezone_offset,
                 strain=w.strain) for w in rows if w.score_state in (None, "SCORED")]
