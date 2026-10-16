"""Quick check: print your most recent WHOOP recovery, sleep and strain (no database needed)."""
import sys

import _bootstrap  # noqa: F401

from src import config
from src.ingestion.token_store import FileTokenStore
from src.ingestion.whoop_client import WhoopClient


def main() -> None:
    store = FileTokenStore(config.WHOOP_TOKEN_DIR)
    users = store.list_users()
    if not users:
        sys.exit("No connected WHOOP account. Run `make server` and open http://localhost:8000/login.")
    client = WhoopClient(users[0], store)

    rec = next(client.recoveries(), None)
    if rec and rec.get("score"):
        s = rec["score"]
        print(f"Recovery {s.get('recovery_score')}% | HRV {s.get('hrv_rmssd_milli', 0):.1f} ms | "
              f"RHR {s.get('resting_heart_rate')} bpm")
    slp = next(client.sleeps(), None)
    if slp and slp.get("score"):
        print(f"Sleep performance {slp['score'].get('sleep_performance_percentage')}%")
    cyc = next(client.cycles(), None)
    if cyc and cyc.get("score"):
        print(f"Day strain {cyc['score'].get('strain', 0):.1f}")


if __name__ == "__main__":
    main()
