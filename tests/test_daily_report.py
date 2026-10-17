from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.report.daily import build_daily_summary, free_windows, recovery_zone
from src.report.render import render_email

TZ = "America/Los_Angeles"
Z = ZoneInfo(TZ)
TODAY = date(2026, 10, 16)


def panel(last_recovery=80, last_sleep=420):
    days = [TODAY - timedelta(days=k) for k in range(31, 0, -1)]
    df = pd.DataFrame({
        "recovery_score": [50.0 + (i % 10) for i in range(len(days))],
        "hrv_rmssd_milli": [50.0] * len(days),
        "resting_heart_rate": [55.0] * len(days),
        "sleep_performance_pct": [85.0] * len(days),
        "total_sleep_min": [480.0] * len(days),
        "deep_min": [90.0] * len(days),
        "rem_min": [100.0] * len(days),
        "load": [10.0] * len(days),
    }, index=pd.Index(days, name="day"))
    df.loc[TODAY - timedelta(days=1), ["recovery_score", "total_sleep_min"]] = [last_recovery, last_sleep]
    return df


def at(h, m=0):
    return datetime(2026, 10, 16, h, m, tzinfo=Z)


def test_recovery_zones_match_whoop():
    assert recovery_zone(67) == "green"
    assert recovery_zone(66) == "yellow"
    assert recovery_zone(33) == "red"
    assert recovery_zone(None) is None


def test_free_windows_between_events():
    events = [dict(start=at(9), end=at(10)), dict(start=at(10, 15), end=at(12)), dict(start=at(15), end=at(16))]
    w = free_windows(events, TODAY, TZ)
    assert [(x["start"], x["end"]) for x in w] == [("08:00", "09:00"), ("12:00", "15:00"), ("16:00", "20:00")]
    # From 13:00 onward only the remaining gaps count.
    w = free_windows(events, TODAY, TZ, now=at(13))
    assert w[0]["start"] == "13:00"


def test_summary_compares_with_own_baseline_and_picks_a_focus():
    events = [dict(start=at(9), end=at(17), attendee_count=3)]
    s = build_daily_summary(panel(), TODAY, TZ, events, now=at(8))
    rec = s["metrics"][0]
    assert rec["value"] == 80 and rec["status"] == "better"
    assert s["recovery_zone"] == "green"
    sleep = next(m for m in s["metrics"] if m["key"] == "total_sleep_min")
    assert sleep["delta"] == -60 and sleep["status"] == "worse"
    assert s["calendar"]["busy_hours"] == 8
    f = s["focus"]
    assert f["focus"] == "go_hard" and f["block"]["start"] == "17:00" and f["block"]["end"] == "18:00"
    subject, html, text = render_email(s)
    assert "Recovery 80%" in subject and "Good day for a hard session" in subject and "Free" in text
    assert "Today&#x27;s focus" in html or "Today's focus" in html
    assert ">80</span>" in html and "Green" in html and "RECOVERY LAB" in html and "{" not in html


def test_missing_last_night_is_reported():
    df = panel().drop(index=TODAY - timedelta(days=1))
    s = build_daily_summary(df, TODAY, TZ, None)
    assert s["last_night_scored"] is False
    subject, html, _ = render_email(s)
    assert "not scored" in subject and "not scored yet" in html and "{" not in html


def test_hrv_chart_and_focus_details_render():
    events = [dict(start=at(9), end=at(17), attendee_count=3)]
    s = build_daily_summary(panel(), TODAY, TZ, events, now=at(8))
    assert len(s["signals"]["hrv_daily"]) == 14
    _, html, text = render_email(s)
    assert "HRV, last 14 nights" in html and html.count("border-radius:3px 3px 0 0") >= 5
    assert "TODAY'S FOCUS" in text
