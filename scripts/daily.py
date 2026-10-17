"""Daily job: sync WHOOP and Google Calendar, build the morning report, email it.

    make daily              # send now if due (respects your report time)
    make daily-now          # send now regardless of the schedule
    make report-preview     # save the HTML to data/reports/ instead of sending

GitHub Actions runs this every 30 minutes (.github/workflows/daily.yml). Each user gets at
most one report per local day, sent after their chosen time and, by default, once last
night's sleep is scored (see src/report/schedule.py). Set the time with `make settings`.

This is a thin command-line wrapper around src/pipeline/daily.py, where the stages live.
The repository is public, so nothing here prints health or calendar values.
"""
import argparse
import os
import sys

import _bootstrap  # noqa: F401

from src import config
from src.db.schema import ensure_schema
from src.db.session import make_session_factory
from src.gcal.google_auth import connected_users
from src.ingestion.token_store import get_whoop_store
from src.pipeline.daily import DailyPipeline
from src.settings import Settings


def masked(user_id: str) -> str:
    return f"user ...{str(user_id)[-3:]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--now", action="store_true", help="send immediately, ignoring the schedule")
    group.add_argument("--preview", action="store_true", help="save the report locally instead of emailing it")
    args = parser.parse_args()
    mode = "preview" if args.preview else "now" if args.now else "scheduled"

    settings = Settings.from_env()
    factory = make_session_factory(settings.require("database_url"))
    ensure_schema(factory.kw["bind"])  # adds tables/columns from newer versions; no-op otherwise
    store = get_whoop_store()
    if not store.list_users():
        sys.exit(f"No connected WHOOP account in the configured token store (TOKEN_STORE={settings.token_store}).")

    pipeline = DailyPipeline(session_factory=factory, settings=settings, whoop_store=store,
                             google_users=set(connected_users()), preview_dir=config.REPORT_DIR)
    failed = False
    for run in pipeline.run_all(mode):
        steps = f" [{'; '.join(run.steps)}]" if run.steps else ""
        detail = run.detail
        if run.outcome == "previewed":
            detail = os.path.relpath(detail, config.PROJECT_ROOT)
        print(f"{masked(run.user_id)}: {run.outcome}{' (' + detail + ')' if detail else ''}{steps}")
        if run.trace and not os.getenv("GITHUB_ACTIONS"):  # local runs only: tracebacks may contain data
            print(run.trace)
        failed |= not run.ok
    # A non-zero exit makes GitHub email you about the failed run as a backup alert.
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
