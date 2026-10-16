"""Show or change your report preferences.

    make settings                                  # show current settings
    make settings ARGS="--time 10:30"              # earliest time to send (local time)
    make settings ARGS="--latest 12:00"            # send by then even if sleep is unscored
    make settings ARGS="--no-wait"                 # send at --time without waiting for the sleep score
    make settings ARGS="--off"                     # pause daily emails (--on to resume)
"""
import argparse
import sys

import _bootstrap  # noqa: F401

from src import config
from src.db.models import Base, User, UserSettings
from src.db.session import SessionLocal, engine
from src.db.upsert import upsert
from src.ingestion.token_store import get_whoop_store
from src.report.schedule import ReportSchedule, parse_hhmm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", help="WHOOP user id (default: the only connected user)")
    parser.add_argument("--time", help="earliest local send time, e.g. 10:30")
    parser.add_argument("--latest", help="latest local send time if sleep is not scored yet")
    wait = parser.add_mutually_exclusive_group()
    wait.add_argument("--wait", dest="wait", action="store_true", default=None)
    wait.add_argument("--no-wait", dest="wait", action="store_false")
    onoff = parser.add_mutually_exclusive_group()
    onoff.add_argument("--on", dest="enabled", action="store_true", default=None)
    onoff.add_argument("--off", dest="enabled", action="store_false")
    args = parser.parse_args()

    users = get_whoop_store().list_users()
    user_id = args.user or (users[0] if len(users) == 1 else None)
    if user_id is None:
        sys.exit(f"Pass --user (connected users: {', '.join(users) or 'none'}).")

    changes = {}
    try:
        if args.time:
            changes["report_time"] = parse_hhmm(args.time)
        if args.latest:
            changes["latest_time"] = parse_hhmm(args.latest)
    except ValueError as exc:
        sys.exit(str(exc))
    if args.wait is not None:
        changes["wait_for_sleep"] = args.wait
    if args.enabled is not None:
        changes["report_enabled"] = args.enabled

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if changes:
            upsert(session, UserSettings, [dict(user_id=int(user_id), **changes)], ["user_id"])
            session.commit()
        s = ReportSchedule.from_row(session.get(UserSettings, int(user_id)))
        user = session.get(User, int(user_id))
        tz = (user.timezone if user and user.timezone else None) or config.REPORT_TIMEZONE

    if s.latest_time <= s.report_time and s.wait_for_sleep:
        print("Note: latest time is not after the report time, so the report will not wait for sleep.")
    print(f"Daily report: {'on' if s.enabled else 'off'}  (timezone {tz})")
    if s.wait_for_sleep:
        print(f"  Sent after {s.report_time:%H:%M}, as soon as last night's sleep is scored, "
              f"and no later than about {s.latest_time:%H:%M}.")
    else:
        print(f"  Sent shortly after {s.report_time:%H:%M}.")
    print("  The job checks every 30 minutes, and GitHub can start runs a few minutes late.")
    if s.last_report_on:
        print(f"  Last sent: {s.last_report_on}")


if __name__ == "__main__":
    main()
