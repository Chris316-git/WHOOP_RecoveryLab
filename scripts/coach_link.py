"""Print a link to the coach chat (valid for 3 days), without waiting for the morning email.

    make coach-link

Needs PUBLIC_BASE_URL and ACTION_SIGNING_KEY in .env (the same values as on the web host).
"""
import sys
import time
from datetime import date

import _bootstrap  # noqa: F401

from src.actions.tokens import ActionToken, sign
from src.ingestion.token_store import get_whoop_store
from src.settings import Settings


def main() -> None:
    s = Settings.from_env()
    if not s.actions_enabled:
        sys.exit("Set PUBLIC_BASE_URL and ACTION_SIGNING_KEY in .env first (same values as on Render).")
    users = get_whoop_store().list_users()
    if not users:
        sys.exit("No connected WHOOP account.")
    token = sign(ActionToken(int(users[0]), date.today(), "coach", int(time.time()) + 3 * 86400),
                 s.action_signing_key)
    print(f"{s.public_base_url}/coach/{token}")


if __name__ == "__main__":
    main()
