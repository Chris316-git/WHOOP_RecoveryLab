from datetime import date, datetime, timezone

from src.analysis.panel import build_panel, cycle_day, parse_offset, sleep_day


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


def test_build_panel_joins_recovery_and_skips_naps():
    sleeps = [
        dict(id="s1", start=utc(2026, 10, 15, 6, 0), end=utc(2026, 10, 15, 14, 0), timezone_offset="-07:00",
             nap=False, score_state="SCORED", in_bed_min=480, light_min=250, deep_min=90, rem_min=100,
             sleep_performance_pct=90, sleep_efficiency_pct=92, respiratory_rate=15),
        dict(id="nap", start=utc(2026, 10, 15, 21, 0), end=utc(2026, 10, 15, 21, 30), timezone_offset="-07:00",
             nap=True, score_state="SCORED", in_bed_min=30),
    ]
    recoveries = [dict(sleep_id="s1", score_state="SCORED", recovery_score=71, hrv_rmssd_milli=55.5,
                       resting_heart_rate=52, user_calibrating=False)]
    cycles = [dict(start=utc(2026, 10, 14, 14, 0), end=utc(2026, 10, 15, 14, 0), timezone_offset="-07:00",
                   score_state="SCORED", strain=12.3)]
    panel = build_panel(sleeps, recoveries, cycles)
    assert list(panel.index) == [date(2026, 10, 14)]
    row = panel.loc[date(2026, 10, 14)]
    assert row["recovery_score"] == 71
    assert row["total_sleep_min"] == 440
    assert row["strain"] == 12.3
