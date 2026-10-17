import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.reasoning.engine import reason
from src.reasoning.evidence import build_case
from src.report.daily import build_daily_summary

TZ = "America/Los_Angeles"
Z = ZoneInfo(TZ)
TODAY = date(2026, 10, 18)
NOW = datetime(2026, 10, 18, 9, 15, tzinfo=Z)


def panel():
    days = [TODAY - timedelta(days=k) for k in range(45, 0, -1)]
    n = len(days)
    df = pd.DataFrame({
        "recovery_score": [60.0 + (i % 7) for i in range(n)], "hrv_rmssd_milli": [108.0 + (i % 5) for i in range(n)],
        "resting_heart_rate": [53.0 + (i % 3) * 0.5 for i in range(n)], "sleep_performance_pct": [80.0] * n,
        "total_sleep_min": [400.0 + (i % 4) * 10 for i in range(n)], "deep_min": [100.0] * n, "rem_min": [95.0] * n,
        "load": [11.0] * n, "sleep_need_baseline_min": [465.0] * n,
        "sleep_start_local": [pd.Timestamp(datetime(d.year, d.month, d.day, 23, 30)) for d in days],
    }, index=pd.Index(days, name="day"))
    last7 = days[-7:]
    df.loc[last7, "hrv_rmssd_milli"] = [92, 96, 90, 98, 94, 97, 105.2]
    df.loc[last7, "total_sleep_min"] = [380, 370, 385, 360, 390, 375, 340]
    df.loc[TODAY - timedelta(days=1), ["recovery_score", "load"]] = [54, 15.5]
    return df


EVENTS = [dict(start=datetime(2026, 10, 18, 9, 0, tzinfo=Z), end=datetime(2026, 10, 18, 10, 30, tzinfo=Z),
               attendee_count=3)]
HISTORY = [dict(day=(TODAY - timedelta(days=k)).isoformat(), focus="prioritize_sleep",
                title="Protect your sleep tonight", block=dict(start="22:15", end="23:00", title="Wind down"),
                response=None, outcome="not_done",
                outcome_detail=dict(bedtime="00:10", target="23:00", minutes_late=70)) for k in (1, 2, 3)]


def setup():
    p = panel()
    s = build_daily_summary(p, TODAY, TZ, EVENTS, now=NOW)
    return s, build_case(s, p, TODAY, NOW, habits=None, recent_plans=HISTORY)


def ai(**overrides):
    out = dict(
        focus_type="prioritize_sleep", title="A small step toward earlier sleep",
        headline="Earlier nights have not stuck lately, so try starting your wind-down 20 minutes earlier tonight.",
        confidence="moderate",
        reasons=[dict(text="You have been short on sleep most nights this week.", evidence=["E1"])],
        counter=[], action=dict(type="calendar_block", title="Wind down: lights low, no screens",
                                start="22:40", minutes=40),
        uncertainty=None, hypothesis="The 23:00 target may have been too far from your usual bedtime.",
    )
    out.update(overrides)
    return out


def run(out):
    s, case = setup()
    return reason(case, s, "key", call=lambda key, model, data: json.dumps(out))


def test_case_file_is_numbered_and_includes_history():
    s, case = setup()
    texts = [e["text"] for e in case["evidence"]]
    assert all(e["id"] == f"E{i}" for i, e in enumerate(case["evidence"], 1))
    assert any("Recovery today: 54%" in t for t in texts)
    assert any("not done, in bed at 00:10 vs target 23:00" in t and "no response" in t for t in texts)
    assert any("Free from now on: 10:30-24:00" in t for t in texts)
    assert case["constraints"]["usual_bedtime"] == "23:30" and case["constraints"]["hard_session_allowed"] is False


def test_valid_ai_recommendation_is_used_with_its_own_action():
    r = run(ai())
    assert r["status"] == "ok", r["problems"]
    f = r["focus"]
    assert f["engine"] == "ai" and f["title"] == "A small step toward earlier sleep"
    assert f["block"] == dict(start="22:40", end="23:20", minutes=40, title="Wind down: lights low, no screens")
    assert f["schedulable"] and "may have been" in f["alternatives"][0]


def test_validator_rejects_unsafe_or_invented_answers():
    cases = {
        "evidence ids": ai(reasons=[dict(text="Short on sleep.", evidence=["E99"])]),
        "numbers": ai(headline="Your sleep dropped 37% this week."),
        "hard session against the data": ai(focus_type="go_hard", action=dict(
            type="calendar_block", title="Intervals", start="16:00", minutes=45)),
        "block not in free time": ai(focus_type="lower_intensity", action=dict(
            type="calendar_block", title="Easy walk", start="09:30", minutes=30)),
        "banned wording": ai(headline="Consider a melatonin supplement tonight."),
        "unhedged hypothesis": ai(hypothesis="You ignore bedtime advice."),
        "block in the past": ai(focus_type="lower_intensity", action=dict(
            type="calendar_block", title="Easy walk", start="08:00", minutes=30)),
    }
    for expected, out in cases.items():
        r = run(out)
        assert r["status"] == "rejected" and expected in r["problems"], (expected, r["problems"])


def test_errors_and_garbage_fall_back():
    s, case = setup()
    assert reason(case, s, "key", call=lambda *a: "no json here")["status"] == "error"

    def boom(*a):
        raise TimeoutError

    assert reason(case, s, "key", call=boom)["problems"] == ["TimeoutError"]


def test_no_change_day_is_a_valid_answer():
    r = run(ai(focus_type="none", title="Nothing needs to change today", headline="Keep your normal plan today.",
               confidence=None, reasons=[], action=dict(type="none"), hypothesis=None))
    assert r["status"] == "ok" and r["focus"]["block"] is None and not r["focus"]["schedulable"]


def test_sleep_focus_needs_a_wind_down_block_and_short_reasons():
    r = run(ai(action=dict(type="guidance", title="Go to bed a bit earlier")))
    assert r["status"] == "rejected" and "missing calendar block" in r["problems"]
    many = [dict(text="Short on sleep.", evidence=["E1"])] * 4
    assert "reasons count" in run(ai(reasons=many))["problems"]
    assert "banned wording" in run(ai(headline="Your body looks under-recovered."))["problems"]
    s, case = setup()
    assert case["constraints"]["default_target_bedtime"] == "23:00"


def test_wind_down_after_midnight_is_tonight():
    r = run(ai(headline="Start winding down a little earlier than your 00:10 bedtimes.", hypothesis=None,
               action=dict(type="calendar_block", title="Wind down", start="00:10", minutes=40)))
    assert r["status"] == "ok", r["problems"]
    assert r["focus"]["block"]["start"] == "00:10" and r["focus"]["block"]["end"] == "00:50"


def test_ai_must_not_contradict_a_control_night():
    s, case = setup()
    case["constraints"]["experiment_tonight"] = "control"
    out = ai(action=dict(type="calendar_block", title="Wind down: screens off", start="22:40", minutes=40))
    r = reason(case, s, "key", call=lambda *a: json.dumps(out))
    assert r["status"] == "rejected" and "conflicts with experiment" in r["problems"]
