"""Run a personal experiment.

    uv run python scripts/experiment.py list                        # available experiments
    uv run python scripts/experiment.py start screens_off_30        # starts tonight (or tomorrow after 18:00)
    uv run python scripts/experiment.py start screens_off_30 --nights 20 --start 2026-10-20
    uv run python scripts/experiment.py status                      # schedule, answers so far, result if done
    uv run python scripts/experiment.py stop                        # stop the active experiment early

The daily email then shows tonight's assignment, asks one Yes/No question after each
screen-free night, and reports the result after the last night.
"""
import argparse
import secrets
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import _bootstrap  # noqa: F401
from sqlalchemy import select

from src import config
from src.db.models import Experiment, User, UserSettings
from src.db.schema import ensure_schema
from src.db.session import SessionLocal, engine
from src.experiments.design import make_schedule
from src.experiments.presets import PRESETS, preset
from src.ingestion.token_store import get_whoop_store
from src.report.data import load_active_experiment
from src.report.schedule import resolve_timezone


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["list", "start", "status", "stop"])
    parser.add_argument("preset", nargs="?")
    parser.add_argument("--nights", type=int, help="even number, default from the preset (14)")
    parser.add_argument("--start", help="first night as YYYY-MM-DD (default: tonight, or tomorrow after 18:00)")
    parser.add_argument("--user", help="WHOOP user id (default: the only connected user)")
    args = parser.parse_args()

    if args.command == "list":
        for key, p in PRESETS.items():
            print(f"{key:18s} {p['title']} ({p['nights']} nights). {p['question']}")
        return

    users = get_whoop_store().list_users()
    user_id = int(args.user or (users[0] if len(users) == 1 else 0)) or sys.exit("Pass --user.")
    ensure_schema(engine)
    with SessionLocal() as session:
        active = load_active_experiment(session, user_id)
        if args.command == "start":
            if active:
                sys.exit("An experiment is already running. Stop it first (experiment.py stop).")
            spec = preset(args.preset or "screens_off_30")
            row, user = session.get(UserSettings, user_id), session.get(User, user_id)
            tz = resolve_timezone(row.timezone if row else None, user.timezone if user else None,
                                  config.REPORT_TIMEZONE)
            now = datetime.now(ZoneInfo(tz))
            start = (date.fromisoformat(args.start) if args.start
                     else now.date() + timedelta(days=1 if now.hour >= 18 else 0))
            nights, seed = args.nights or spec["nights"], secrets.randbelow(2**31)
            schedule = make_schedule(start, nights, seed)
            session.add(Experiment(user_id=user_id, preset=args.preset or "screens_off_30", start_day=start,
                                   nights=nights, seed=seed, schedule=schedule, status="active"))
            session.commit()
            print(f"Started \"{spec['title']}\": {nights} nights from {start}. Assignments are random and "
                  f"revealed one night at a time in the daily email.")
        elif args.command == "stop":
            if not active:
                sys.exit("No active experiment.")
            e = session.get(Experiment, active[0]["id"])
            e.status, e.ended_at = "stopped", datetime.now(timezone.utc)
            session.commit()
            print("Stopped. Its data stays stored; no result is computed for a stopped experiment.")
        else:
            if not active:
                last = session.scalars(select(Experiment).where(Experiment.user_id == user_id)
                                       .order_by(Experiment.id.desc())).first()
                if last is None:
                    print("No experiments yet. Start one with: experiment.py start screens_off_30")
                else:
                    print(f"Last experiment ({last.preset}) is {last.status}.")
                    if last.result:
                        r = last.result["primary"]["itt"]
                        print(f"Result: {r['verdict']}, effect {r['effect']} (95% interval {r['ci']}), "
                              f"{r['pairs']} pairs, p = {r['p']}")
                return
            exp, answers = active
            print(f"{preset(exp['preset'])['title']}: {exp['nights']} nights from {exp['start_day']}")
            today = date.today().isoformat()
            for s in exp["schedule"]:   # past nights only, so tonight's coin flip stays a surprise
                if s["day"] < today:
                    print(f"  {s['day']}  {s['arm']:9s}  answer: {answers.get(s['day'], '-')}")


if __name__ == "__main__":
    main()
