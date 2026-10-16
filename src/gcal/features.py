"""Turn a day's calendar time blocks into numeric features. Pure logic, no I/O."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ACTIVE_START = time(8, 0)   # window used for "longest free block"
ACTIVE_END = time(20, 0)
BACK_TO_BACK_GAP_MIN = 10   # a gap this short or shorter counts as back-to-back


@dataclass
class Block:
    start: datetime
    end: datetime
    attendee_count: int = 0


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[list[datetime]] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _minutes(td: timedelta) -> float:
    return td.total_seconds() / 60


def daily_features(day: date, blocks: list[Block], tz: str) -> dict:
    """Features for one local calendar day. `blocks` should be timed (not all-day), busy events."""
    zone = ZoneInfo(tz)
    day_start = datetime.combine(day, time.min, zone)
    day_end = day_start + timedelta(days=1)

    # Clip each block to this day so events crossing midnight are split correctly.
    clipped = []
    for b in blocks:
        s, e = max(b.start, day_start), min(b.end, day_end)
        if e > s:
            clipped.append(Block(s, e, b.attendee_count))
    clipped.sort(key=lambda b: b.start)

    merged = _merge([(b.start, b.end) for b in clipped])
    busy = sum(_minutes(e - s) for s, e in merged)
    meetings = _merge([(b.start, b.end) for b in clipped if b.attendee_count >= 2])
    meeting_min = sum(_minutes(e - s) for s, e in meetings)

    # Longest free block within the active window.
    win_start = datetime.combine(day, ACTIVE_START, zone)
    win_end = datetime.combine(day, ACTIVE_END, zone)
    cursor, longest = win_start, 0.0
    for s, e in merged:
        s, e = max(s, win_start), min(e, win_end)
        if e <= s:
            continue
        longest = max(longest, _minutes(s - cursor))
        cursor = max(cursor, e)
    longest = max(longest, _minutes(win_end - cursor)) if cursor < win_end else longest

    back_to_back = sum(
        1 for prev, nxt in zip(clipped, clipped[1:])
        if 0 <= _minutes(nxt.start - prev.end) <= BACK_TO_BACK_GAP_MIN
    )

    def local_minutes(dt: datetime) -> int:
        local = dt.astimezone(zone)
        return int(_minutes(local - datetime.combine(day, time.min, zone)))

    return dict(
        day=day,
        event_count=len(clipped),
        busy_minutes=round(busy, 1),
        meeting_minutes=round(meeting_min, 1),
        first_start_min=local_minutes(merged[0][0]) if merged else None,
        last_end_min=local_minutes(merged[-1][1]) if merged else None,
        longest_free_block_min=round(longest, 1),
        back_to_back_count=back_to_back,
        is_weekend=day.weekday() >= 5,
    )
