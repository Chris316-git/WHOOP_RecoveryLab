"""See or remove what Recovery Lab remembers about you (goals, preferences, constraints,
corrections you told the coach).

    make memory                      # list
    make memory ARGS="--forget 3"    # forget item 3
    make memory ARGS="--delete-all"  # remove everything, including forgotten items
"""
import argparse

import _bootstrap  # noqa: F401

from src.db.schema import ensure_schema
from src.db.session import make_session_factory
from src.ingestion.token_store import get_whoop_store
from src.memory import store
from src.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forget", type=int)
    parser.add_argument("--delete-all", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    factory = make_session_factory(settings.require("database_url"))
    ensure_schema(factory.kw["bind"])
    uid = int(get_whoop_store().list_users()[0])
    with factory() as session:
        if args.delete_all:
            print(f"Deleted {store.delete_all(session, uid)} items.")
            return
        if args.forget is not None:
            print("Forgotten." if store.forget(session, uid, args.forget) else "No such active item.")
        items = store.active(session, uid)
    if not items:
        print("Nothing remembered yet. Tell the coach your goals, preferences or constraints.")
    for m in items:
        print(f"  [{m['id']}] {m['kind']:<10} {m['text']}  (since {m['since']})")


if __name__ == "__main__":
    main()
