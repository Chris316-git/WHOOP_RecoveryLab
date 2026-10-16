"""Daily job: sync WHOOP and Google Calendar, build the morning report, email it.

    make daily              # send now if due (respects your report time)
    make daily-now          # send now regardless of the schedule
    make report-preview     # save the HTML to data/reports/ instead of sending

GitHub Actions runs this every 30 minutes (.github/workflows/daily.yml). Each user gets at
most one report per local day, sent after their chosen time and, by default, once last
night's sleep is scored (see src/report/schedule.py). Set the time with `make settings`.

The repository is public, so this script never prints health or calendar values.
"""
import argparse
import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import _bootstrap  # noqa: F401

from src import config
from src.db.models import Base, User, UserSettings
from src.db.session import SessionLocal, engine
from src.db.upsert import upsert
from src.gcal.google_auth import connected_users
from src.gcal.sync import sync_calendar
from src.ingestion.sync import sync_user
from src.ingestion.token_store import get_whoop_store
from src.ingestion.whoop_client import WhoopClient
from src.report.daily import build_daily_summary
from src.report.data import load_events_for_day, load_recent_panel
from src.report.render import render_email
from src.report.schedule import ReportSchedule, in_window, ready_to_send


def _masked(user_id: str) -> str:
    return f"user ...{str(user_id)[-3:]}"


def _short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160] if str(exc) else ''}"


def _user_context(user_id: str) -> tuple[str, ReportSchedule]:
    with SessionLocal() as session:
        user = session.get(User, int(user_id))
        tz = (user.timezone if user and user.timezone else None) or config.REPORT_TIMEZONE
        schedule = ReportSchedule.from_row(session.get(UserSettings, int(user_id)))
    return tz, schedule


def run_for_user(user_id: str, store, google_users: set[str], mode: str) -> bool:
    """mode: "scheduled" (respect the schedule), "now" (send immediately), "preview".
    Returns False if something went wrong in a run that produced a report."""
    label = _masked(user_id)
    tz, schedule = _user_context(user_id)
    now = datetime.now(ZoneInfo(tz))
    if mode == "scheduled":
        due, reason = in_window(schedule, now)
        if not due:
            print(f"{label}: skipped ({reason})")
            return True

    notices: list[str] = []
    try:
        with SessionLocal() as session:
            sync_user(WhoopClient(user_id, store), session)
        print(f"{label}: WHOOP synced")
    except Exception as exc:  # keep going: an older report is better than none
        notices.append("WHOOP sync failed; showing the latest stored data. If this repeats, "
                       "re-authorize WHOOP locally (make server, /login).")
        print(f"{label}: WHOOP sync failed ({_short_error(exc)})")

    if user_id in google_users:
        try:
            with SessionLocal() as session:
                sync_calendar(int(user_id), session)
            print(f"{label}: calendar synced")
        except Exception as exc:
            notices.append("Google Calendar sync failed (authorization may have expired). "
                           "Run make connect-google locally.")
            print(f"{label}: calendar sync failed ({_short_error(exc)})")

    now = datetime.now(ZoneInfo(tz))
    with SessionLocal() as session:
        panel = load_recent_panel(session, int(user_id), now.date())
        events = load_events_for_day(session, int(user_id), now.date(), tz) if user_id in google_users else None
    summary = build_daily_summary(panel, now.date(), tz, events, now=now)

    if mode == "scheduled":
        ready, reason = ready_to_send(schedule, now, summary["last_night_scored"])
        if not ready:
            print(f"{label}: {reason}; will check again in 30 minutes")
            return True
        print(f"{label}: {reason}")

    subject, html, text = render_email(summary, notices)
    if mode == "preview":
        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = config.REPORT_DIR / f"{summary['date']}-{user_id}.html"
        path.write_text(html)
        path.with_suffix(".txt").write_text(text)
        print(f"{label}: report saved to {path.relative_to(config.PROJECT_ROOT)}")
        return not notices

    from src.notify.emailer import send_email
    send_email(config.require("REPORT_EMAIL_TO"), subject, html, text)
    with SessionLocal() as session:
        upsert(session, UserSettings, [dict(user_id=int(user_id), last_report_on=now.date())], ["user_id"])
        session.commit()
    print(f"{label}: report emailed")
    return not notices


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--now", action="store_true", help="send immediately, ignoring the schedule")
    group.add_argument("--preview", action="store_true", help="save the report locally instead of emailing it")
    args = parser.parse_args()
    mode = "preview" if args.preview else "now" if args.now else "scheduled"

    Base.metadata.create_all(engine)  # creates tables added in newer versions; no-op otherwise
    store = get_whoop_store()
    users = store.list_users()
    if not users:
        sys.exit("No connected WHOOP account in the configured token store "
                 f"(TOKEN_STORE={config.TOKEN_STORE}).")
    google_users = set(connected_users())

    failed = False
    for user_id in users:
        try:
            failed |= not run_for_user(user_id, store, google_users, mode)
        except Exception as exc:
            failed = True
            print(f"{_masked(user_id)}: report failed ({_short_error(exc)})")
            if not os.getenv("GITHUB_ACTIONS"):  # local runs only: tracebacks may contain data
                traceback.print_exc()
    # A non-zero exit makes GitHub email you about the failed run as a backup alert.
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
