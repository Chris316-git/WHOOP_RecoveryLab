"""Pull WHOOP data and upsert it into the database.

First run: full history backfill. Later runs: incremental, re-fetching the last few
days because WHOOP can re-score recent records after they are first created.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.db.models import Cycle, Recovery, Sleep, User, Workout
from src.db.upsert import upsert
from src.ingestion.whoop_client import WhoopClient
from src.ingestion.whoop_mappers import cycle_row, recovery_row, sleep_row, workout_row

OVERLAP_DAYS = 3


def _batched(iterable, size=200):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _sync_start(session: Session, model, user_id: int, time_col) -> datetime | None:
    """None means full backfill; otherwise resume a few days before the latest record."""
    latest = session.scalar(select(func.max(time_col)).where(model.user_id == user_id))
    return latest - timedelta(days=OVERLAP_DAYS) if latest else None


def sync_user(client: WhoopClient, session: Session) -> dict[str, int]:
    profile = client.profile()
    user_id = int(profile["user_id"])
    upsert(session, User, [dict(user_id=user_id, first_name=profile.get("first_name"))], ["user_id"])
    session.commit()

    jobs = [
        ("cycles", Cycle, client.cycles, cycle_row, ["id"], Cycle.start),
        ("recoveries", Recovery, client.recoveries, recovery_row, ["cycle_id"], Recovery.created_at),
        ("sleeps", Sleep, client.sleeps, sleep_row, ["id"], Sleep.start),
        ("workouts", Workout, client.workouts, workout_row, ["id"], Workout.start),
    ]
    counts = {}
    for name, model, fetch, to_row, keys, time_col in jobs:
        start = _sync_start(session, model, user_id, time_col)
        total = 0
        for batch in _batched(fetch(start=start)):
            total += upsert(session, model, [to_row(r) for r in batch], keys)
            session.commit()
        counts[name] = total

    session.execute(
        update(User).where(User.user_id == user_id).values(last_synced_at=datetime.now(timezone.utc))
    )
    session.commit()
    return counts
