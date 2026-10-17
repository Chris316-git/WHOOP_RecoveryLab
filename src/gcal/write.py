"""Write confirmed blocks to the app's own "Recovery Lab" Google calendar.

Uses the narrow calendar.app.created scope: the app can create its own secondary calendar and
manage events there, but cannot read or change the user's other calendars' events through it.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CALENDAR_NAME = "Recovery Lab"
REMINDER_MINUTES = 15


def event_body(day: date, block: dict, tz: str, focus_title: str, reasons: list[str],
               reminder_minutes: int = REMINDER_MINUTES, busy: bool = True) -> dict:
    """Google Calendar event resource for one block. Pure logic.

    `busy=False` marks the event as free: a wind-down reminder should not block the evening
    for anyone looking at your availability."""
    zone = ZoneInfo(tz)
    h, m = map(int, block["start"].split(":"))
    if h < 5:   # e.g. a wind-down starting at 00:15 belongs to the night after `day`
        day = day + timedelta(days=1)
    start = datetime.combine(day, time(h % 24, m), zone)
    end = start + timedelta(minutes=int(block["minutes"]))
    why = "\n".join(f"- {r}" for r in reasons)
    return {
        "summary": block["title"],
        "description": f"{focus_title}\n\nWhy:\n{why}\n\nAdded by Recovery Lab from today's suggestion.",
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "transparency": "opaque" if busy else "transparent",
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": reminder_minutes}]},
        "extendedProperties": {"private": {"recoveryLabDay": day.isoformat()}},
    }


def ensure_calendar(service, calendar_id: str | None, tz: str) -> str:
    """Return the app's calendar id, creating the calendar if it does not exist (or was deleted)."""
    from googleapiclient.errors import HttpError
    if calendar_id:
        try:
            service.calendars().get(calendarId=calendar_id).execute()
            return calendar_id
        except HttpError as exc:
            if exc.resp.status not in (403, 404, 410):
                raise
    created = service.calendars().insert(body={"summary": CALENDAR_NAME, "timeZone": tz,
                                               "description": "Blocks you added from Recovery Lab."}).execute()
    return created["id"]


def create_event(service, calendar_id: str, body: dict) -> str:
    return service.events().insert(calendarId=calendar_id, body=body).execute()["id"]


def update_event(service, calendar_id: str, event_id: str, body: dict) -> str:
    return service.events().update(calendarId=calendar_id, eventId=event_id, body=body).execute()["id"]


def delete_event(service, calendar_id: str, event_id: str) -> None:
    from googleapiclient.errors import HttpError
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        if exc.resp.status not in (404, 410):  # already gone is fine
            raise
