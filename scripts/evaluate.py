"""How is the AI reasoning engine doing? Prints a small report from stored plans.

    uv run python scripts/evaluate.py            # the last 30 days
    uv run python scripts/evaluate.py --days 90

Run it locally: the report contains your own aggregate numbers, so do not paste it into
public logs.
"""
import argparse
import json
from datetime import date, timedelta

import _bootstrap  # noqa: F401
from sqlalchemy import select

from src.db.models import DailyPlan
from src.db.schema import ensure_schema
from src.db.session import SessionLocal, engine
from src.reasoning.evaluate import evaluate_plans

COLUMNS = ("engine", "focus", "rule_focus", "ai_status", "ai_problems", "ai_output", "evidence", "response", "outcome")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    ensure_schema(engine)
    since = date.today() - timedelta(days=args.days)
    with SessionLocal() as session:
        rows = session.scalars(select(DailyPlan).where(DailyPlan.day >= since))
        plans = [{c: getattr(p, c) for c in COLUMNS} for p in rows]
    print(json.dumps(evaluate_plans(plans), indent=2))


if __name__ == "__main__":
    main()
