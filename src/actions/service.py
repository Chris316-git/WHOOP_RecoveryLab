"""What happens when a user clicks Add to calendar, Change time, Dismiss, Undo or Not useful.

Dependencies are injected (session factory, calendar, clock) so the same logic runs in the web
endpoint and in tests. Every action looks at the plan's current state first, so a repeated
click (or a page reload) never does the same thing twice.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.actions.options import slot_options
from src.actions.tokens import ActionToken
from src.db.models import DailyPlan, UserSettings
from src.planner.focus import TITLES
from src.report.daily import free_windows
from src.report.data import load_events_for_day


class GoogleCalendar:
    """Writes to the user's "Recovery Lab" calendar. `add` returns None when the user has not
    granted write access (older Google authorization)."""

    def _service(self, user_id: int, need_write: bool = True):
        from googleapiclient.discovery import build

        from src.gcal.google_auth import can_write, load_credentials
        creds = load_credentials(str(user_id))
        if need_write and not can_write(creds):
            return None
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @staticmethod
    def _body(day, tz, block, focus, title, reasons):
        from src.gcal.write import event_body
        return event_body(day, block, tz, title, reasons, busy=focus != "prioritize_sleep")

    def add(self, user_id, day, tz, block, focus, title, reasons, calendar_id):
        from src.gcal.write import create_event, ensure_calendar
        service = self._service(user_id)
        if service is None:
            return None
        cal_id = ensure_calendar(service, calendar_id, tz)
        return cal_id, create_event(service, cal_id, self._body(day, tz, block, focus, title, reasons))

    def move(self, user_id, calendar_id, event_id, day, tz, block, focus, title, reasons):
        from src.gcal.write import update_event
        update_event(self._service(user_id), calendar_id, event_id, self._body(day, tz, block, focus, title, reasons))

    def remove(self, user_id, calendar_id, event_id):
        from src.gcal.write import delete_event
        delete_event(self._service(user_id), calendar_id, event_id)


class PlanNotFound(LookupError):
    pass


@dataclass
class Outcome:
    status: str                     # added | moved | dismissed | not_useful | undone | already | nothing
    message: str
    block: dict | None = None
    calendar: str | None = None     # added | not_connected | failed | None
    can_undo: bool = False
    ask_not_useful: bool = False    # offer the optional "the suggestion itself was off" button
    extra: dict = field(default_factory=dict)


CALENDAR_MESSAGES = {
    "added": "On your Recovery Lab calendar, with a reminder 15 minutes before.",
    "not_connected": "Noted. To have it put on your calendar, re-run `make connect-google` once so "
                     "Recovery Lab may manage its own calendar.",
    "failed": "Noted, but the calendar could not be updated right now.",
}


@dataclass
class ActionService:
    session_factory: Callable
    calendar: object = field(default_factory=GoogleCalendar)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    default_tz: str = "America/Los_Angeles"

    # ---- reading ----
    def plan(self, token: ActionToken) -> dict:
        with self.session_factory() as session:
            p = session.get(DailyPlan, (token.user_id, token.day))
            if p is None:
                raise PlanNotFound("No plan found for this link.")
            return dict(focus=p.focus, title=TITLES.get(p.focus, p.focus), reasons=p.reasons or [],
                        block=p.block, response=p.response, calendar_status=p.calendar_status,
                        final_block=p.final_block, calendar_id=p.calendar_id, event_id=p.event_id,
                        timezone=p.timezone or self.default_tz)

    def options(self, token: ActionToken) -> list[dict]:
        plan = self.plan(token)
        if not plan["block"]:
            return []
        tz = plan["timezone"]
        now = self.clock().astimezone(ZoneInfo(tz))
        with self.session_factory() as session:
            events = load_events_for_day(session, token.user_id, token.day, tz)
        current = plan["final_block"] if plan["calendar_status"] == "scheduled" else plan["block"]
        start_from = now if now.date() == token.day else None
        return slot_options(current, free_windows(events, token.day, tz, start_from), plan["focus"])

    # ---- writing ----
    def _save(self, token: ActionToken, **fields) -> None:
        with self.session_factory() as session:
            p = session.get(DailyPlan, (token.user_id, token.day))
            for k, v in fields.items():
                setattr(p, k, v)
            p.decided_at = self.clock()
            if fields.get("calendar_id"):
                row = session.get(UserSettings, token.user_id)
                if row is None:
                    session.add(UserSettings(user_id=token.user_id, rl_calendar_id=fields["calendar_id"]))
                else:
                    row.rl_calendar_id = fields["calendar_id"]
            session.commit()

    def _remove_event(self, token: ActionToken, plan: dict) -> bool:
        """Take the event off the calendar. False when that failed (the plan keeps its event)."""
        if plan["calendar_status"] != "scheduled" or not plan["event_id"]:
            return True
        try:
            self.calendar.remove(token.user_id, plan["calendar_id"], plan["event_id"])
            return True
        except Exception:
            return False

    def add(self, token: ActionToken, block: dict | None = None) -> Outcome:
        plan = self.plan(token)
        if not plan["block"]:
            return Outcome("nothing", "There is nothing to schedule for this day.")
        scheduled = plan["calendar_status"] == "scheduled"
        if scheduled and block is None:
            return Outcome("already", "This is already on your calendar.", plan["final_block"], can_undo=True)
        chosen = block or plan["block"]
        args = (token.day, plan["timezone"], chosen, plan["focus"], plan["title"], plan["reasons"])
        if scheduled:  # Change time on something already added: move the event
            try:
                self.calendar.move(token.user_id, plan["calendar_id"], plan["event_id"], *args)
            except Exception:
                return Outcome("already", CALENDAR_MESSAGES["failed"], plan["final_block"], "failed", can_undo=True)
            self._save(token, final_block=chosen, response="added")
            return Outcome("moved", CALENDAR_MESSAGES["added"], chosen, "added", can_undo=True)
        with self.session_factory() as session:
            settings = session.get(UserSettings, token.user_id)
            current_cal = settings.rl_calendar_id if settings else None
        try:
            written = self.calendar.add(token.user_id, *args, current_cal)
            calendar = "not_connected" if written is None else "added"
        except Exception:
            written, calendar = None, "failed"
        if written:
            cal_id, event_id = written
            self._save(token, response="added", calendar_status="scheduled", final_block=chosen,
                       calendar_id=cal_id, event_id=event_id)
        else:
            self._save(token, response="added", final_block=chosen)
        return Outcome("added", CALENDAR_MESSAGES[calendar], chosen, calendar, can_undo=written is not None)

    def change(self, token: ActionToken, choice: int) -> Outcome:
        options = self.options(token)
        if not 0 <= choice < len(options):
            return Outcome("nothing", "That time is no longer available. Open the link again to see current options.")
        return self.add(token, {k: v for k, v in options[choice].items() if k != "label"})

    def dismiss(self, token: ActionToken, not_useful: bool = False) -> Outcome:
        plan = self.plan(token)
        response = "not_useful" if not_useful else "dismissed"
        if plan["response"] == response:
            return Outcome("already", "Already dismissed.", can_undo=True, ask_not_useful=not not_useful)
        fields = dict(response=response)
        if plan["calendar_status"] == "scheduled" and self._remove_event(token, plan):
            fields["calendar_status"] = "removed"
        self._save(token, **fields)
        if not_useful:
            return Outcome("not_useful", "Thanks. For the next two weeks, this kind of suggestion "
                                         "will need stronger evidence before it comes back.", can_undo=True)
        return Outcome("dismissed", "No problem. Nothing else to do.", can_undo=True, ask_not_useful=True)

    def undo(self, token: ActionToken) -> Outcome:
        plan = self.plan(token)
        if plan["calendar_status"] == "scheduled":
            if not self._remove_event(token, plan):
                return Outcome("already", "The calendar could not be updated right now. Try again later.",
                               plan["final_block"], "failed", can_undo=True)
            self._save(token, response=None, calendar_status="removed")
            return Outcome("undone", "Removed from your calendar.")
        if plan["response"] is not None:
            self._save(token, response=None)
            return Outcome("undone", "Undone. Today's suggestion is open again.")
        return Outcome("nothing", "Nothing to undo.")
