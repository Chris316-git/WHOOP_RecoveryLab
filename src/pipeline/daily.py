"""The daily pipeline as separate, injectable stages.

    due?  ->  sync sources  ->  build report (+ check yesterday)  ->  ready?  ->  record  ->  deliver

Every dependency (database sessions, settings, token store, mail sender, clock) is passed
in, so the stages can be reused from a script, a web endpoint, a notebook or a test, and
each one can be run on its own. Nothing here prints health or calendar values: stage
results carry statuses only, because the scheduled job's logs are public.
"""
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.db.models import DailyPlan, User, UserSettings
from src.db.upsert import upsert
from src.feedback.outcome import evaluate
from src.planner.focus import TITLES
from src.report.daily import build_daily_summary
from src.report.data import (
    load_events_for_day,
    load_not_useful,
    load_plan,
    load_recent_focuses,
    load_recent_panel,
)
from src.report.render import render_email
from src.report.schedule import (
    ReportSchedule,
    in_window,
    ready_to_send,
    resolve_timezone,
)
from src.settings import Settings

Sender = Callable[[str, str, str, str], None]   # (to, subject, html, text)
Clock = Callable[[ZoneInfo], datetime]


def _system_clock(zone: ZoneInfo) -> datetime:
    return datetime.now(zone)


def short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160] if str(exc) else ''}"


@dataclass
class UserRun:
    """What happened for one user. Statuses only, safe to log."""
    user_id: str
    outcome: str = "pending"        # skipped | waiting | sent | previewed | failed
    detail: str = ""
    notices: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    trace: str = ""                 # full traceback on failure; print locally only (may contain data)

    @property
    def ok(self) -> bool:
        return self.outcome in ("skipped", "waiting") or (self.outcome in ("sent", "previewed") and not self.notices)


@dataclass
class DailyPipeline:
    session_factory: Callable
    settings: Settings
    whoop_store: object                              # FileTokenStore or DbTokenStore
    google_users: set[str] = field(default_factory=set)
    sender: Sender | None = None                     # defaults to SMTP from settings
    clock: Clock = _system_clock
    preview_dir: Path | None = None

    # ---- stage 0: context ----
    def context(self, user_id: str) -> tuple[str, ReportSchedule]:
        with self.session_factory() as session:
            user = session.get(User, int(user_id))
            row = session.get(UserSettings, int(user_id))
            tz = resolve_timezone(row.timezone if row else None, user.timezone if user else None,
                                  self.settings.report_timezone)
            return tz, ReportSchedule.from_row(row)

    # ---- stage 1: sync ----
    def sync_sources(self, user_id: str, run: UserRun) -> None:
        from src.gcal.sync import sync_calendar
        from src.ingestion.sync import sync_user
        from src.ingestion.whoop_client import WhoopClient
        try:
            with self.session_factory() as session:
                sync_user(WhoopClient(user_id, self.whoop_store), session)
            run.steps.append("whoop synced")
        except Exception as exc:  # keep going: an older report is better than none
            run.notices.append("WHOOP sync failed; showing the latest stored data. If this repeats, "
                               "re-authorize WHOOP locally (make server, /login).")
            run.steps.append(f"whoop sync failed ({short_error(exc)})")
        if user_id in self.google_users:
            try:
                with self.session_factory() as session:
                    sync_calendar(int(user_id), session)
                run.steps.append("calendar synced")
            except Exception as exc:
                run.notices.append("Google Calendar sync failed (authorization may have expired). "
                                   "Run make connect-google locally.")
                run.steps.append(f"calendar sync failed ({short_error(exc)})")

    # ---- stage 2: build ----
    def build_summary(self, user_id: str, tz: str, now: datetime) -> dict:
        today, uid = now.date(), int(user_id)
        with self.session_factory() as session:
            panel = load_recent_panel(session, uid, today)
            events = load_events_for_day(session, uid, today, tz) if user_id in self.google_users else None
            recent = load_recent_focuses(session, uid, today)
            muted = load_not_useful(session, uid, today)
            yesterday = load_plan(session, uid, today - timedelta(days=1))
        summary = build_daily_summary(panel, today, tz, events, now=now, recent_focuses=recent, not_useful=muted)
        # Did yesterday's focus happen? Read from the wearable data, so nobody has to check in.
        if yesterday is not None:
            yesterday["title"] = TITLES.get(yesterday["focus"], yesterday["focus"])
            summary["yesterday"] = evaluate(yesterday, panel, today - timedelta(days=1))
        return summary

    # ---- stage 3: deliver ----
    def deliver(self, summary: dict, notices: list[str]) -> None:
        subject, html, text = render_email(summary, notices)
        send = self.sender
        if send is None:
            from src.notify.emailer import send_email
            send = lambda to, s, h, t: send_email(to, s, h, t, self.settings.smtp)  # noqa: E731
        send(self.settings.require("report_email_to"), subject, html, text)

    def save_preview(self, user_id: str, summary: dict, notices: list[str]) -> Path:
        _, html, text = render_email(summary, notices)
        directory = self.preview_dir or Path("data/reports")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{summary['date']}-{user_id}.html"
        path.write_text(html)
        path.with_suffix(".txt").write_text(text)
        return path

    # ---- stage 4: record ----
    def save_plan(self, user_id: str, summary: dict, now: datetime, tz: str) -> str:
        """Store today's focus before sending (the email's links point at it). A plan the user
        already decided on is left alone. Returns the plan's status."""
        f = summary["focus"]
        with self.session_factory() as session:
            existing = session.get(DailyPlan, (int(user_id), now.date()))
            if existing is not None and (existing.response or existing.calendar_status):
                return "decided"
            upsert(session, DailyPlan, [dict(
                user_id=int(user_id), day=now.date(), focus=f["focus"], score=float(f["score"]),
                reasons=f["reasons"], block=f["block"], considered=[list(c) for c in f["considered"]],
                timezone=tz,
            )], ["user_id", "day"])
            session.commit()
        return "open"

    def save_outcome(self, user_id: str, summary: dict, now: datetime) -> None:
        """Store what the wearable says about yesterday's focus on yesterday's plan."""
        review = summary.get("yesterday")
        if not review:
            return
        with self.session_factory() as session:
            p = session.get(DailyPlan, (int(user_id), now.date() - timedelta(days=1)))
            if p is None:
                return
            p.outcome = review["outcome"]
            p.outcome_detail = dict(review["detail"], recovery_before=review["recovery_before"],
                                    recovery_after=review["recovery_after"])
            p.outcome_checked_at = datetime.now(timezone.utc)
            session.commit()

    def action_links(self, user_id: str, summary: dict, now: datetime) -> dict | None:
        """Signed links, valid until 06:00 the next morning. Add to calendar / Change time /
        Dismiss only when a time block actually helps; otherwise just a quiet "Not useful?"."""
        focus = summary["focus"]
        if not self.settings.actions_enabled or focus.get("focus") in (None, "none"):
            return None
        actions = ("add", "change", "dismiss") if focus.get("schedulable") else ("not_useful",)
        from datetime import time

        from src.actions.tokens import ActionToken, sign
        expires = int(datetime.combine(now.date() + timedelta(days=1), time(6), now.tzinfo).timestamp())
        base, key = self.settings.public_base_url, self.settings.action_signing_key
        return {a: f"{base}/a/{sign(ActionToken(int(user_id), now.date(), a, expires), key)}"
                for a in actions}

    def mark_sent(self, user_id: str, now: datetime) -> None:
        with self.session_factory() as session:
            upsert(session, UserSettings, [dict(user_id=int(user_id), last_report_on=now.date())], ["user_id"])
            session.commit()

    # ---- the whole flow for one user ----
    def run_user(self, user_id: str, mode: str = "scheduled") -> UserRun:
        """mode: "scheduled" (respect the user's schedule), "now" or "preview"."""
        run = UserRun(user_id)
        tz, schedule = self.context(user_id)
        zone = ZoneInfo(tz)
        if mode == "scheduled":
            due, reason = in_window(schedule, self.clock(zone))
            if not due:
                run.outcome, run.detail = "skipped", reason
                return run
        self.sync_sources(user_id, run)
        now = self.clock(zone)
        summary = self.build_summary(user_id, tz, now)
        if mode == "scheduled":
            ready, reason = ready_to_send(schedule, now, summary["last_night_scored"])
            if not ready:
                run.outcome, run.detail = "waiting", reason
                return run
            run.detail = reason
        if mode == "preview":
            path = self.save_preview(user_id, summary, run.notices)
            run.outcome, run.detail = "previewed", str(path)
            return run
        status = self.save_plan(user_id, summary, now, tz)
        self.save_outcome(user_id, summary, now)
        if status == "open":
            summary["actions"] = self.action_links(user_id, summary, now)
        self.deliver(summary, run.notices)
        self.mark_sent(user_id, now)
        run.outcome = "sent"
        return run

    def run_all(self, mode: str = "scheduled") -> list[UserRun]:
        runs = []
        for user_id in self.whoop_store.list_users():
            try:
                runs.append(self.run_user(user_id, mode))
            except Exception as exc:
                runs.append(UserRun(user_id, outcome="failed", detail=short_error(exc),
                                    trace=traceback.format_exc()))
        return runs
