"""Sync Google Calendar time blocks and compute daily schedule features.

Privacy: only start/end, busy/free, all-day flag, recurrence flag and attendee COUNT
are stored. Titles, descriptions, locations and attendee identities are discarded.
"""
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from googleapiclient.discovery import build
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from src import config
from src.db.models import CalendarEvent, DailyCalendarFeatures, User
from src.db.upsert import upsert
from src.gcal.features import Block, daily_features
from src.gcal.google_auth import load_credentials

DEFAULT_PAST_DAYS = 365
FUTURE_DAYS = 14


def _event_key(calendar_id: str, event_id: str) -> str:
    # Hash the calendar id so personal email addresses are not stored.
    cal_hash = hashlib.sha256(calendar_id.encode()).hexdigest()[:12]
    return f"{cal_hash}:{event_id}"


def _declined_by_me(event: dict) -> bool:
    return any(a.get("self") and a.get("responseStatus") == "declined" for a in event.get("attendees", []))


def _to_row(user_id: int, calendar_id: str, event: dict) -> dict | None:
    if event.get("status") == "cancelled" or _declined_by_me(event):
        return None
    start, end = event.get("start", {}), event.get("end", {})
    all_day = "date" in start
    if all_day:
        s = datetime.fromisoformat(start["date"]).replace(tzinfo=timezone.utc)
        e = datetime.fromisoformat(end["date"]).replace(tzinfo=timezone.utc)
    else:
        s = datetime.fromisoformat(start["dateTime"])
        e = datetime.fromisoformat(end["dateTime"])
    return dict(
        user_id=user_id,
        event_key=_event_key(calendar_id, event["id"]),
        start=s,
        end=e,
        all_day=all_day,
        is_busy=event.get("transparency") != "transparent",
        attendee_count=len(event.get("attendees", [])),
        is_recurring="recurringEventId" in event,
    )


def _fetch_events(service, calendar_id: str, time_min: datetime, time_max: datetime):
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,  # expand recurring events into individual instances
            orderBy="startTime",
            maxResults=2500,
            pageToken=page_token,
        ).execute()
        yield from resp.get("items", [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def sync_calendar(user_id: int, session: Session, past_days: int = DEFAULT_PAST_DAYS) -> dict:
    creds = load_credentials(str(user_id))
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    tz = service.settings().get(setting="timezone").execute()["value"]
    session.execute(update(User).where(User.user_id == user_id).values(timezone=tz))

    now = datetime.now(timezone.utc)
    time_min, time_max = now - timedelta(days=past_days), now + timedelta(days=FUTURE_DAYS)

    # Replace events in the window so deleted or declined events disappear too.
    session.execute(
        delete(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start >= time_min,
            CalendarEvent.start < time_max,
        )
    )
    rows = []
    for cal_id in config.GOOGLE_CALENDAR_IDS:
        for event in _fetch_events(service, cal_id, time_min, time_max):
            row = _to_row(user_id, cal_id, event)
            if row:
                rows.append(row)
    for i in range(0, len(rows), 500):
        upsert(session, CalendarEvent, rows[i:i + 500], ["user_id", "event_key"])

    # Daily features from timed, busy events.
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(tz)
    by_day: dict[date, list[Block]] = defaultdict(list)
    for r in rows:
        if r["all_day"] or not r["is_busy"]:
            continue
        d, last = r["start"].astimezone(zone).date(), r["end"].astimezone(zone).date()
        while d <= last:  # events crossing midnight count toward each day they touch
            by_day[d].append(Block(r["start"], r["end"], r["attendee_count"]))
            d += timedelta(days=1)

    first_day, last_day = time_min.astimezone(zone).date(), time_max.astimezone(zone).date()
    feature_rows, d = [], first_day
    while d <= last_day:
        feature_rows.append({"user_id": user_id, **daily_features(d, by_day.get(d, []), tz)})
        d += timedelta(days=1)
    upsert(session, DailyCalendarFeatures, feature_rows, ["user_id", "day"])
    session.commit()
    return {"events": len(rows), "days": len(feature_rows), "timezone": tz}
