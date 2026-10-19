"""Glue between the web page and the coach: who the user is, signed proposals, calendar writes.

The browser keeps the conversation; the server stores none of it. A proposal travels to the
browser signed (HMAC with ACTION_SIGNING_KEY), so the "Add to calendar" request cannot be
edited, and it is checked again against the calendar right before writing.
"""
import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.coach import tools as T
from src.coach.agent import DEFAULT_MODEL, Toolbox, chat

PROPOSAL_TTL = 36 * 3600
DAILY_MESSAGES = 40   # per user per day, to cap API cost


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def seal(payload: dict, key: str) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return body + "." + _b64(hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()[:16])


def unseal(text: str, key: str, now: float | None = None) -> dict:
    try:
        body, sig = text.split(".", 1)
    except (ValueError, AttributeError):
        raise ValueError("malformed") from None
    good = _b64(hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()[:16])
    if not hmac.compare_digest(sig, good):
        raise ValueError("not valid")
    payload = json.loads(_unb64(body))
    if (now if now is not None else time.time()) > payload.get("exp", 0):
        raise ValueError("expired")
    return payload


@dataclass
class CoachService:
    session_factory: Callable
    signing_key: str
    api_key: str
    model: str = DEFAULT_MODEL
    calendar: object = None                  # GoogleCalendar() by default
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    default_tz: str = "America/Los_Angeles"
    call: Callable | None = None             # tests inject a fake model
    data_factory: Callable | None = None     # tests inject a fake CoachData
    usage: dict = field(default_factory=dict)

    def _tz(self, user_id: int) -> str:
        from src.db.models import User, UserSettings
        from src.report.schedule import resolve_timezone
        with self.session_factory() as session:
            row, user = session.get(UserSettings, user_id), session.get(User, user_id)
            return resolve_timezone(row.timezone if row else None, user.timezone if user else None, self.default_tz)

    def _data(self, user_id: int):
        tz = self._tz(user_id)
        now = self.clock().astimezone(ZoneInfo(tz))
        if self.data_factory:
            return self.data_factory(user_id, tz, now)
        return T.CoachData(self.session_factory, user_id, tz, now)

    def message(self, user_id: int, history: list[dict]) -> dict:
        data = self._data(user_id)
        key = (user_id, data.now.date())
        self.usage[key] = self.usage.get(key, 0) + 1
        if self.usage[key] > DAILY_MESSAGES:
            return dict(reply="That's enough coaching for today. Come back tomorrow.", proposals=[], remembered=[],
                        tools_used=[], checked=True)
        result = chat(history, Toolbox(data), self.api_key, self.model, call=self.call)
        exp = int(time.time()) + PROPOSAL_TTL
        result["proposals"] = [dict(p, token=seal(dict(p, user=user_id, exp=exp), self.signing_key))
                               for p in result["proposals"]]
        result["remembered"] = [dict(m, token=seal(dict(user=user_id, memory=m["id"], exp=exp), self.signing_key))
                                for m in result.get("remembered") or []]
        return result

    def forget(self, user_id: int, token: str) -> dict:
        from src.memory import store
        try:
            t = unseal(token, self.signing_key)
        except ValueError as exc:
            return dict(ok=False, message=f"This link is {exc}.")
        if t.get("user") != user_id:
            return dict(ok=False, message="This belongs to another link.")
        with self.session_factory() as session:
            done = store.forget(session, user_id, int(t["memory"]))
        return dict(ok=done, message="Forgotten." if done else "Already forgotten.")

    def add(self, user_id: int, token: str) -> dict:
        """Write a proposed block to the user's Recovery Lab calendar, after checking it again."""
        from src.db.models import UserSettings
        try:
            p = unseal(token, self.signing_key)
        except ValueError as exc:
            return dict(ok=False, message=f"This suggestion is {exc}. Ask the coach again.")
        if p.get("user") != user_id:
            return dict(ok=False, message="This suggestion belongs to another link.")
        data = self._data(user_id)
        day = date.fromisoformat(p["day"])
        windows = T.free_time(data.events(day), day, data.tz, data.now)["free_windows"]
        problems = T.check_block(day, p["start"], p["minutes"], p["title"], p["kind"], windows, data.now,
                                 hard_allowed=True)   # safety was checked when proposed; time can change
        if problems:
            return dict(ok=False, message="That time no longer works (" + problems[0] + "). Ask the coach for "
                                          "another time.")
        calendar = self.calendar
        if calendar is None:
            from src.actions.service import GoogleCalendar
            calendar = GoogleCalendar()
        with self.session_factory() as session:
            row = session.get(UserSettings, user_id)
            current = row.rl_calendar_id if row else None
        block = dict(start=p["start"], end=p["end"], minutes=p["minutes"], title=p["title"])
        focus = "prioritize_sleep" if p["kind"] == "wind_down" else "coach"   # a wind-down is shown as free
        try:
            written = calendar.add(user_id, day, data.tz, block, focus, "Planned with the Recovery Lab coach",
                                   [p["why"]] if p.get("why") else [], current)
        except Exception as exc:
            from src.actions.service import _calendar_error
            return dict(ok=False, message=f"The calendar could not be updated right now ({_calendar_error(exc)}).")
        if written is None:
            return dict(ok=False, message="Recovery Lab may not write to your calendar yet: run make connect-google "
                                          "once.")
        cal_id, event_id = written
        if cal_id != current:
            with self.session_factory() as session:
                row = session.get(UserSettings, user_id)
                if row is None:
                    session.add(UserSettings(user_id=user_id, rl_calendar_id=cal_id))
                else:
                    row.rl_calendar_id = cal_id
                session.commit()
        undo = seal(dict(user=user_id, cal=cal_id, event=event_id, exp=int(time.time()) + PROPOSAL_TTL),
                    self.signing_key)
        return dict(ok=True, message=f"Added: {p['day']} {p['start']}-{p['end']} {p['title']}.", undo=undo)

    def undo(self, user_id: int, token: str) -> dict:
        try:
            u = unseal(token, self.signing_key)
        except ValueError as exc:
            return dict(ok=False, message=f"This undo link is {exc}.")
        if u.get("user") != user_id:
            return dict(ok=False, message="This belongs to another link.")
        calendar = self.calendar
        if calendar is None:
            from src.actions.service import GoogleCalendar
            calendar = GoogleCalendar()
        try:
            calendar.remove(user_id, u["cal"], u["event"])
        except Exception as exc:
            from src.actions.service import _calendar_error
            return dict(ok=False, message=f"Could not remove it right now ({_calendar_error(exc)}).")
        return dict(ok=True, message="Removed from your calendar.")
