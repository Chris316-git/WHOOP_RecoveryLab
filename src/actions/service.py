"""What happens when a user clicks Add to calendar, Change time, Dismiss, Undo or Not useful.

Dependencies are injected (session factory, calendar, clock) so the same logic runs in the web
endpoint and in tests. Every action looks at the plan's current state first, so a repeated
click (or a page reload) never does the same thing twice.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.actions.options import slot_options
from src.actions.tokens import ActionToken
from src.db.models import DailyPlan, Experiment, ExperimentDay, UserSettings
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


log = logging.getLogger("recovery_lab.actions")


def _calendar_error(exc: Exception) -> str:
    """Log the full error for the host's logs; return a short, data-free label for the page."""
    log.exception("calendar write failed")
    status = getattr(getattr(exc, "resp", None), "status", None)  # googleapiclient HttpError
    return f"{type(exc).__name__}{f' {status}' if status else ''}"


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
    "failed": "Noted, but the calendar could not be updated right now. Tap the button in the email again "
              "to retry.",
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
            return dict(focus=p.focus, title=p.title or TITLES.get(p.focus, p.focus), reasons=p.reasons or [],
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
        except Exception as exc:
            _calendar_error(exc)
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
            except Exception as exc:
                return Outcome("already", f"{CALENDAR_MESSAGES['failed']} ({_calendar_error(exc)})",
                               plan["final_block"], "failed", can_undo=True)
            self._save(token, final_block=chosen, response="added")
            return Outcome("moved", CALENDAR_MESSAGES["added"], chosen, "added", can_undo=True)
        with self.session_factory() as session:
            settings = session.get(UserSettings, token.user_id)
            current_cal = settings.rl_calendar_id if settings else None
        error = None
        try:
            written = self.calendar.add(token.user_id, *args, current_cal)
            calendar = "not_connected" if written is None else "added"
        except Exception as exc:
            written, calendar, error = None, "failed", _calendar_error(exc)
        if written:
            cal_id, event_id = written
            self._save(token, response="added", calendar_status="scheduled", final_block=chosen,
                       calendar_id=cal_id, event_id=event_id)
        else:
            self._save(token, response="added", final_block=chosen)
        message = CALENDAR_MESSAGES[calendar] + (f" ({error})" if error else "")
        return Outcome("added", message, chosen, calendar, can_undo=written is not None)

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

    # ---- experiments ----
    def adhere(self, token: ActionToken, yes: bool) -> Outcome:
        """Record the user's answer for one experiment night. Answering again overwrites it."""
        from sqlalchemy import select

        with self.session_factory() as session:
            experiments = session.scalars(select(Experiment).where(Experiment.user_id == token.user_id)
                                          .order_by(Experiment.id.desc()))
            exp = next((e for e in experiments if any(s["day"] == token.day.isoformat() for s in e.schedule)), None)
            if exp is None:
                raise PlanNotFound("No experiment found for this link.")
            if exp.status != "active":
                return Outcome("already", "This experiment has already ended.")
            row = session.get(ExperimentDay, (exp.id, token.day))
            if row is None:
                row = ExperimentDay(experiment_id=exp.id, day=token.day)
                session.add(row)
            row.adherence, row.answered_at = ("yes" if yes else "no"), self.clock()
            session.commit()
        if yes:
            return Outcome("recorded", "Noted: you kept to the plan last night. Thanks.")
        return Outcome("recorded", "Noted: not last night. That is useful too; the analysis accounts for it.")

    def _user_today(self, session, user_id: int):
        """The user's local date and hour, from their saved time zone."""
        from src.db.models import User
        from src.report.schedule import resolve_timezone
        row, user = session.get(UserSettings, user_id), session.get(User, user_id)
        tz = resolve_timezone(row.timezone if row else None, user.timezone if user else None, self.default_tz)
        now = self.clock().astimezone(ZoneInfo(tz))
        return now.date(), now.hour

    def _find(self, session, user_id: int, **where):
        from sqlalchemy import select
        q = select(Experiment).where(Experiment.user_id == user_id)
        for k, v in where.items():
            q = q.where(getattr(Experiment, k) == v)
        return session.scalars(q.order_by(Experiment.id.desc())).first()

    def _activate(self, session, exp: Experiment) -> str:
        """Start now: tonight if before 18:00 local time, otherwise tomorrow."""
        from datetime import timedelta

        from src.experiments.design import make_schedule
        if self._find(session, exp.user_id, status="active") is not None:
            return "Another experiment is already running. Stop it first, or wait until it ends."
        today, hour = self._user_today(session, exp.user_id)
        start = today + timedelta(days=1 if hour >= 18 else 0)
        exp.start_day, exp.status = start, "active"
        exp.schedule = make_schedule(start, exp.nights, exp.seed)
        session.commit()
        when = "tonight" if start == today else "tomorrow"
        return f"Started. It begins {when} and runs {exp.nights} nights; each morning's email tells you the plan."

    def start_proposed(self, token: ActionToken) -> Outcome:
        with self.session_factory() as session:
            exp = self._find(session, token.user_id, status="proposed", proposed_on=token.day)
            if exp is None:
                return Outcome("already", "This suggestion is no longer open.")
            return Outcome("started", self._activate(session, exp))

    def start_preset(self, token: ActionToken, key: str) -> Outcome:
        import secrets

        from src.experiments.presets import PRESETS
        if key not in PRESETS:
            return Outcome("nothing", "Unknown experiment.")
        with self.session_factory() as session:
            exp = Experiment(user_id=token.user_id, preset=key, start_day=token.day, nights=PRESETS[key]["nights"],
                             seed=secrets.randbelow(2**31), schedule=[], status="proposed", extensions=0)
            session.add(exp)
            session.flush()
            message = self._activate(session, exp)
            if exp.status != "active":
                session.rollback()
                return Outcome("already", message)
            return Outcome("started", message)

    def decline(self, token: ActionToken) -> Outcome:
        with self.session_factory() as session:
            exp = self._find(session, token.user_id, status="proposed", proposed_on=token.day)
            if exp is not None:
                exp.status, exp.ended_at = "declined", self.clock()
                session.commit()
        return Outcome("declined_exp", "No problem. This experiment will not be suggested again for a month.")

    def decide(self, token: ActionToken, step: str) -> Outcome:
        """keep / drop a finished experiment, or extend it by a few more pairs of nights."""
        from datetime import timedelta

        from src.experiments.design import make_schedule
        from src.experiments.presets import EXTENSION_NIGHTS, MAX_EXTENSIONS
        with self.session_factory() as session:
            exp = self._find(session, token.user_id, start_day=token.day)
            if exp is None or exp.status != "completed":
                return Outcome("already", "This experiment is not waiting for a decision.")
            if exp.next_step:
                return Outcome("already", f"Already decided: {exp.next_step}.")
            if step in ("keep", "drop"):
                exp.next_step = step
                session.commit()
                return Outcome("decided", "Kept. Future suggestions will take this habit into account."
                               if step == "keep" else "Dropped. Nothing else to do.")
            if (exp.extensions or 0) >= MAX_EXTENSIONS:
                return Outcome("already", "This experiment has already been extended once.")
            if self._find(session, token.user_id, status="active") is not None:
                return Outcome("already", "Another experiment is already running.")
            today, hour = self._user_today(session, token.user_id)
            start = today + timedelta(days=1 if hour >= 18 else 0)
            pairs = max(s["pair"] for s in exp.schedule) + 1
            extra = make_schedule(start, EXTENSION_NIGHTS, exp.seed + 1 + (exp.extensions or 0))
            exp.schedule = exp.schedule + [dict(s, pair=s["pair"] + pairs) for s in extra]
            exp.nights += EXTENSION_NIGHTS
            exp.extensions = (exp.extensions or 0) + 1
            exp.status, exp.result, exp.ended_at = "active", None, None
            session.commit()
            return Outcome("decided", f"Extended by {EXTENSION_NIGHTS} nights, starting "
                           f"{'tonight' if start == today else 'tomorrow'}. The result will use all nights.")

    def stop_experiment(self, token: ActionToken) -> Outcome:
        with self.session_factory() as session:
            exp = self._find(session, token.user_id, start_day=token.day, status="active")
            if exp is None:
                return Outcome("already", "No running experiment to stop.")
            exp.status, exp.ended_at = "stopped", self.clock()
            session.commit()
        return Outcome("stopped", "Stopped. Its data stays stored; no result is computed for a stopped experiment.")

    def experiment_options(self, token: ActionToken) -> tuple[list[dict], bool]:
        """Presets for the browse page, and whether an experiment is already running."""
        from src.experiments.presets import PRESETS
        with self.session_factory() as session:
            running = self._find(session, token.user_id, status="active") is not None
        return [dict(key=k, **{f: p[f] for f in ("title", "question", "treatment", "nights")})
                for k, p in PRESETS.items()], running
