"""Show or change your report preferences.

    make settings                                  # show current settings
    make settings ARGS="--time 10:30"              # earliest time to send (local time)
    make settings ARGS="--latest 12:00"            # send by then even if sleep is unscored
    make settings ARGS="--no-wait"                 # send at --time without waiting for the sleep score
    make settings ARGS="--off"                     # pause daily emails (--on to resume)
    make settings ARGS="--tz Asia/Shanghai"        # use this time zone (IANA name)
    make settings ARGS="--tz auto"                 # follow your Google Calendar time zone (default)
    make settings ARGS="--sports golf,running"     # activities to suggest, in order of preference
    make settings ARGS="--sports auto"             # learn them from your workouts (default)
"""
import argparse
import sys

import _bootstrap  # noqa: F401

from src import config
from src.db.models import User, UserSettings
from src.db.schema import ensure_schema
from src.db.session import SessionLocal, engine
from src.db.upsert import upsert
from src.ingestion.token_store import get_whoop_store
from src.planner.habits import parse_sports
from src.report.schedule import ReportSchedule, parse_hhmm, resolve_timezone, validate_timezone


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", help="WHOOP user id (default: the only connected user)")
    parser.add_argument("--time", help="earliest local send time, e.g. 10:30")
    parser.add_argument("--latest", help="latest local send time if sleep is not scored yet")
    wait = parser.add_mutually_exclusive_group()
    wait.add_argument("--wait", dest="wait", action="store_true", default=None)
    wait.add_argument("--no-wait", dest="wait", action="store_false")
    parser.add_argument("--tz", help='IANA time zone such as Asia/Shanghai, or "auto" to follow the calendar')
    onoff = parser.add_mutually_exclusive_group()
    onoff.add_argument("--on", dest="enabled", action="store_true", default=None)
    onoff.add_argument("--off", dest="enabled", action="store_false")
    parser.add_argument("--sports", help='activities to suggest, e.g. "golf,running", or "auto"')
    parser.add_argument("--resend", action="store_true",
                        help="forget that today's report was sent, so the scheduled job sends it again")
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
        if args.tz:
            changes["timezone"] = None if args.tz.strip().lower() == "auto" else validate_timezone(args.tz)
    except ValueError as exc:
        sys.exit(str(exc))
    if args.wait is not None:
        changes["wait_for_sleep"] = args.wait
    if args.enabled is not None:
        changes["report_enabled"] = args.enabled
    if args.sports:
        changes["sports"] = None if args.sports.strip().lower() == "auto" else ",".join(parse_sports(args.sports))
    if args.resend:
        changes["last_report_on"] = None

    ensure_schema(engine)
    with SessionLocal() as session:
        if changes:
            upsert(session, UserSettings, [dict(user_id=int(user_id), **changes)], ["user_id"])
            session.commit()
        row = session.get(UserSettings, int(user_id))
        s = ReportSchedule.from_row(row)
        user = session.get(User, int(user_id))
        chosen = row.timezone if row else None
        tz = resolve_timezone(chosen, user.timezone if user else None, config.REPORT_TIMEZONE)

    if s.latest_time <= s.report_time and s.wait_for_sleep:
        print("Note: latest time is not after the report time, so the report will not wait for sleep.")
    source = "set by you" if chosen else "from Google Calendar" if user and user.timezone else "default"
    print(f"Daily report: {'on' if s.enabled else 'off'}  (time zone {tz}, {source})")
    if s.wait_for_sleep:
        print(f"  Sent after {s.report_time:%H:%M}, as soon as last night's sleep is scored, "
              f"and no later than about {s.latest_time:%H:%M}.")
    else:
        print(f"  Sent shortly after {s.report_time:%H:%M}.")
    print("  The job checks every 30 minutes, and GitHub can start runs a few minutes late.")
    sports = row.sports if row and row.sports else "learned from your workouts"
    print(f"Suggested activities: {sports}, placed near the time you usually do them")
    if s.last_report_on:
        print(f"  Last sent: {s.last_report_on}")


if __name__ == "__main__":
    main()
