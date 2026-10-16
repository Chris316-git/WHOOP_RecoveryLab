"""Sync WHOOP data for every connected user. The first run backfills full history."""
import sys
import time

import _bootstrap  # noqa: F401

from src import config
from src.db.session import SessionLocal
from src.ingestion.sync import sync_user
from src.ingestion.token_store import FileTokenStore
from src.ingestion.whoop_client import WhoopClient


def main() -> None:
    store = FileTokenStore(config.WHOOP_TOKEN_DIR)
    users = store.list_users()
    if not users:
        sys.exit("No connected WHOOP account. Run `make server` and open http://localhost:8000/login.")
    for user_id in users:
        started = time.time()
        with SessionLocal() as session:
            counts = sync_user(WhoopClient(user_id, store), session)
        summary = ", ".join(f"{k}: {v}" for k, v in counts.items())
        print(f"User {user_id} synced in {time.time() - started:.1f}s -> {summary}")


if __name__ == "__main__":
    main()
