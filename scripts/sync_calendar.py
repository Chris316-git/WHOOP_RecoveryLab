"""Sync calendar time blocks and daily schedule features for every connected user."""
import _bootstrap  # noqa: F401

from src import config
from src.db.session import SessionLocal
from src.gcal.sync import sync_calendar


def main() -> None:
    users = sorted(p.stem for p in config.GOOGLE_TOKEN_DIR.glob("*.json")) if config.GOOGLE_TOKEN_DIR.exists() else []
    if not users:
        raise SystemExit("No Google Calendar connected. Run `make connect-google` first.")
    for user_id in users:
        with SessionLocal() as session:
            result = sync_calendar(int(user_id), session)
        print(f"User {user_id}: {result['events']} events, {result['days']} days of features ({result['timezone']})")


if __name__ == "__main__":
    main()
