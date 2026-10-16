"""One-time Google Calendar authorization, linked to your WHOOP user."""
import sys

import _bootstrap  # noqa: F401

from src.gcal.google_auth import authorize
from src.ingestion.token_store import get_whoop_store


def main() -> None:
    users = get_whoop_store().list_users()
    if not users:
        sys.exit("Connect WHOOP first (make server, then open http://localhost:8000/login).")
    user_id = users[0]
    authorize(user_id)
    print(f"Google Calendar connected for user {user_id}. Next: make sync-calendar")


if __name__ == "__main__":
    main()
