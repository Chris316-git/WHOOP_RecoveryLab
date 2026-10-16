from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.gcal.features import Block, daily_features

TZ = "America/Los_Angeles"
Z = ZoneInfo(TZ)
D = date(2026, 10, 14)  # a Wednesday


def at(h, m=0):
    return datetime(2026, 10, 14, h, m, tzinfo=Z)


def test_empty_day_is_fully_free():
    f = daily_features(D, [], TZ)
    assert f["busy_minutes"] == 0
    assert f["longest_free_block_min"] == 12 * 60
    assert f["first_start_min"] is None
    assert f["is_weekend"] is False


def test_overlaps_merge_and_back_to_back_counted():
    blocks = [
        Block(at(9), at(10), attendee_count=3),
        Block(at(9, 30), at(10, 30), attendee_count=1),  # overlaps the first
        Block(at(10, 35), at(11), attendee_count=2),     # 5-minute gap -> back-to-back
        Block(at(15), at(16), attendee_count=0),
    ]
    f = daily_features(D, blocks, TZ)
    assert f["busy_minutes"] == 90 + 25 + 60
    assert f["meeting_minutes"] == 60 + 25
    assert f["back_to_back_count"] == 1
    assert f["first_start_min"] == 9 * 60
    assert f["last_end_min"] == 16 * 60
    assert f["longest_free_block_min"] == 4 * 60  # 11:00 -> 15:00


def test_event_crossing_midnight_is_clipped():
    late = Block(datetime(2026, 10, 14, 23, 0, tzinfo=Z), datetime(2026, 10, 15, 1, 0, tzinfo=Z))
    assert daily_features(D, [late], TZ)["busy_minutes"] == 60
    assert daily_features(date(2026, 10, 15), [late], TZ)["busy_minutes"] == 60
