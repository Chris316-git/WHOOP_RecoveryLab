from datetime import date, datetime, timezone

from src.analysis.panel import build_panel
from src.analysis.records import DailyRecord
from src.sources.whoop import cycle_day, daily_records, parse_offset, sleep_day


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_parse_offset():
    assert parse_offset("-07:00") == -420
    assert parse_offset("+05:30") == 330
    assert parse_offset(None) is None


def test_sleep_after_midnight_belongs_to_previous_day():
    # 00:30 local (UTC-7) on Oct 15 -> behavior day Oct 14
    s = {"start": utc(2026, 10, 15, 7, 30), "timezone_offset": "-07:00"}
    assert sleep_day(s) == date(2026, 10, 14)
    # 23:00 local on Oct 14
    s = {"start": utc(2026, 10, 15, 6, 0), "timezone_offset": "-07:00"}
    assert sleep_day(s) == date(2026, 10, 14)


def test_cycle_day_uses_midpoint():
    c = {"start": utc(2026, 10, 14, 14, 0), "end": utc(2026, 10, 15, 14, 0), "timezone_offset": "-07:00"}
    assert cycle_day(c) == date(2026, 10, 14)


SLEEPS = [
    dict(id="s1", start=utc(2026, 10, 15, 6, 0), end=utc(2026, 10, 15, 14, 0), timezone_offset="-07:00",
         nap=False, score_state="SCORED", in_bed_min=480, light_min=250, deep_min=90, rem_min=100,
         sleep_performance_pct=90, sleep_efficiency_pct=92, respiratory_rate=15),
    dict(id="nap", start=utc(2026, 10, 15, 21, 0), end=utc(2026, 10, 15, 21, 30), timezone_offset="-07:00",
         nap=True, score_state="SCORED", in_bed_min=30),
]
RECOVERIES = [dict(sleep_id="s1", score_state="SCORED", recovery_score=71, hrv_rmssd_milli=55.5,
                   resting_heart_rate=52, user_calibrating=False)]
CYCLES = [
    dict(start=utc(2026, 10, 14, 14, 0), end=utc(2026, 10, 15, 14, 0), timezone_offset="-07:00",
         score_state="SCORED", strain=12.3),
    dict(start=utc(2026, 10, 15, 14, 0), end=utc(2026, 10, 16, 14, 0), timezone_offset="-07:00",
         score_state="SCORED", strain=8.0),  # a day with load but no sleep yet
]


def test_whoop_adapter_makes_device_agnostic_records():
    recs = daily_records(SLEEPS, RECOVERIES, CYCLES)
    assert [r.day for r in recs] == [date(2026, 10, 14), date(2026, 10, 15)]
    first = recs[0]
    assert first.source == "whoop" and first.recovery_score == 71 and first.total_sleep_min == 440
    assert first.load == 12.3 and first.calibrating is False and first.source_sleep_id == "s1"
    assert recs[1].total_sleep_min is None and recs[1].load == 8.0


def test_build_panel_is_source_independent():
    panel = build_panel(daily_records(SLEEPS, RECOVERIES, CYCLES))
    row = panel.loc[date(2026, 10, 14)]
    assert row["recovery_score"] == 71 and row["total_sleep_min"] == 440 and row["load"] == 12.3
    # Any other device only has to produce DailyRecords.
    other = build_panel([DailyRecord(day=date(2026, 10, 14), source="oura", hrv_rmssd_milli=48.0,
                                     total_sleep_min=410.0)])
    assert other.loc[date(2026, 10, 14), "hrv_rmssd_milli"] == 48.0
    assert build_panel([]).empty
