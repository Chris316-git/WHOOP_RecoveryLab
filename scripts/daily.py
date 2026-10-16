"""Daily job: sync WHOOP and Google Calendar, build the morning report, email it.

    make daily              # sync + send
    make report-preview     # sync + save the HTML to data/reports/ instead of sending

Runs every morning in GitHub Actions (.github/workflows/daily.yml). The repository is
public, so this script never prints health or calendar values: logs show only status.
"""
import argparse
import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import _bootstrap  # noqa: F401

from src import config
from src.db.models import User
from src.db.session import SessionLocal
from src.gcal.google_auth import connected_users
from src.gcal.sync import sync_calendar
from src.ingestion.sync import sync_user
from src.ingestion.token_store import get_whoop_store
from src.ingestion.whoop_client import WhoopClient
from src.report.daily import build_daily_summary
from src.report.data import load_events_for_day, load_recent_panel
from src.report.render import render_email


def _masked(user_id: str) -> str:
    return f"user ...{str(user_id)[-3:]}"


def _short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160] if str(exc) else ''}"


def run_for_user(user_id: str, store, google_users: set[str], send: bool) -> bool:
    notices: list[str] = []
    label = _masked(user_id)

    try:
        with SessionLocal() as session:
            sync_user(WhoopClient(user_id, store), session)
        print(f"{label}: WHOOP synced")
    except Exception as exc:  # keep going: an older report is better than none
        notices.append("WHOOP sync failed; showing the latest stored data. If this repeats, "
                       "re-authorize WHOOP locally (make server, /login) and run make migrate-tokens.")
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

    with SessionLocal() as session:
        user = session.get(User, int(user_id))
        tz = (user.timezone if user and user.timezone else None) or config.REPORT_TIMEZONE
        now = datetime.now(ZoneInfo(tz))
        panel = load_recent_panel(session, int(user_id), now.date())
        events = load_events_for_day(session, int(user_id), now.date(), tz) if user_id in google_users else None
    summary = build_daily_summary(panel, now.date(), tz, events, now=now)
    subject, html, text = render_email(summary, notices)

    if send:
        from src.notify.emailer import send_email
        send_email(config.require("REPORT_EMAIL_TO"), subject, html, text)
        print(f"{label}: report emailed")
    else:
        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = config.REPORT_DIR / f"{summary['date']}-{user_id}.html"
        path.write_text(html)
        (path.with_suffix(".txt")).write_text(text)
        print(f"{label}: report saved to {path.relative_to(config.PROJECT_ROOT)}")
    return not notices


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", action="store_true", help="save the report locally instead of emailing it")
    args = parser.parse_args()

    store = get_whoop_store()
    users = store.list_users()
    if not users:
        sys.exit("No connected WHOOP account in the configured token store "
                 f"(TOKEN_STORE={config.TOKEN_STORE}).")
    google_users = set(connected_users())

    failed = False
    for user_id in users:
        try:
            ok = run_for_user(user_id, store, google_users, send=not args.preview)
            failed |= not ok
        except Exception as exc:
            failed = True
            print(f"{_masked(user_id)}: report failed ({_short_error(exc)})")
            if not os.getenv("GITHUB_ACTIONS"):  # local runs only: tracebacks may contain data
                traceback.print_exc()
    # A non-zero exit makes GitHub Actions email you about the failed run as a backup alert.
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
