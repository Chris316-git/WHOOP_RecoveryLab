"""Randomized night-by-night schedule. Pure logic.

Nights come in consecutive pairs; within each pair a fair coin decides which night is the
treatment night. This keeps the two arms balanced, never runs one arm for many nights in a
row, and makes slow drifts (a busy week, a cold) cancel out within pairs. The seed is stored,
so the schedule can be reproduced and audited.
"""
import random
from datetime import date, timedelta


def make_schedule(start: date, nights: int, seed: int) -> list[dict]:
    if nights < 4 or nights % 2:
        raise ValueError("nights must be an even number of at least 4")
    rng = random.Random(seed)
    out = []
    for p in range(nights // 2):
        arms = ["treatment", "control"]
        rng.shuffle(arms)
        for k, arm in enumerate(arms):
            out.append(dict(day=(start + timedelta(days=2 * p + k)).isoformat(), arm=arm, pair=p))
    return out


def arm_on(schedule: list[dict], day: date) -> dict | None:
    return next((s for s in schedule if s["day"] == day.isoformat()), None)
