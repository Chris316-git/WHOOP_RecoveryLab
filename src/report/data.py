"""Load what the daily report needs from the database."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.panel import build_panel
from src.db.models import CalendarEvent, Cycle, DailyCalendarFeatures, Recovery, Sleep

HISTORY_DAYS = 45


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
    return build_panel(sleeps, recoveries, cycles, calendar)


def load_events_for_day(session: Session, user_id: int, day: date, tz: str) -> list[dict]:
    """Timed busy events overlapping the local day (time blocks only; no titles exist)."""
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time.min, zone)
    end = start + timedelta(days=1)
    rows = session.scalars(select(CalendarEvent).where(
        CalendarEvent.user_id == user_id, CalendarEvent.start < end, CalendarEvent.end > start,
        CalendarEvent.all_day.is_(False), CalendarEvent.is_busy.is_(True)))
    return [dict(start=r.start, end=r.end, attendee_count=r.attendee_count) for r in rows]
