from datetime import date, datetime, timedelta

import pandas as pd

from src.planner.focus import THRESHOLD, choose_focus, find_slot, usual_bedtime

TODAY = date(2026, 10, 16)


def summary(zone="yellow", recovery=55, signals=None, free=None, busy_hours=3.0, meetings=1,
            sleep_delta=0, rec_status="typical", hrv_status="typical", scored=True):
    return dict(
        last_night_scored=scored,
        recovery_zone=zone,
        metrics=[
            dict(key="recovery_score", value=recovery, status=rec_status, delta=0),
            dict(key="hrv_rmssd_milli", value=50, status=hrv_status, delta=0),
            dict(key="total_sleep_min", value=420, status="typical", delta=sleep_delta),
        ],
        signals=signals or {},
        calendar=dict(free_windows=free if free is not None else [dict(start="12:00", end="20:00", minutes=480)],
                      busy_hours=busy_hours, meeting_count=meetings),
    )


EMPTY = pd.DataFrame()
NORMAL_LOAD = dict(ratio=1.0, consecutive_hard_days=0, level="normal")


def test_all_normal_means_no_change():
    f = choose_focus(summary(signals={"load": NORMAL_LOAD}), EMPTY, TODAY)
    assert f["focus"] == "none" and f["block"] is None and f["score"] < THRESHOLD


def test_high_load_and_low_hrv_lowers_intensity_with_an_easy_slot():
    sig = {"load": dict(ratio=1.55, consecutive_hard_days=3, level="very_high"),
           "hrv": dict(status="below", recent_mean=48, normal_low=55, normal_high=61)}
    f = choose_focus(summary(signals=sig), EMPTY, TODAY)
    assert f["focus"] == "lower_intensity"
    assert any("1.55x" in r for r in f["reasons"]) and any("HRV" in r for r in f["reasons"])
    assert f["block"]["minutes"] == 30 and f["block"]["start"] == "16:00"
    assert f["schedulable"] is False   # "take it easy" is advice, not a calendar event


def test_sleep_debt_turns_into_a_wind_down_before_target_bedtime():
    sig = {"load": NORMAL_LOAD, "sleep": dict(shortfall_min=300, nights_measured=7, nights_short=5)}
    f = choose_focus(summary(signals=sig, sleep_delta=-80), EMPTY, TODAY)
    assert f["focus"] == "prioritize_sleep"
    # default bedtime 23:00 -> target 22:30 -> wind-down 21:45-22:30
    assert (f["block"]["start"], f["block"]["end"]) == ("21:45", "22:30")
    assert "22:30" in f["note"] and f["schedulable"] is True


def test_green_and_fresh_suggests_hard_session_but_not_too_late():
    sig = {"load": dict(ratio=0.7, consecutive_hard_days=0, level="low")}
    f = choose_focus(summary(zone="green", recovery=82, rec_status="better", signals=sig,
                             free=[dict(start="19:00", end="22:00", minutes=180)]), EMPTY, TODAY)
    # the only free time ends too close to bedtime (23:00 - 3 h = 20:00 latest end) -> 19:00-20:00 fits
    assert f["focus"] == "go_hard" and f["block"]["end"] == "20:00"
    late = choose_focus(summary(zone="green", recovery=82, rec_status="better", signals=sig,
                                free=[dict(start="20:30", end="22:00", minutes=90)]), EMPTY, TODAY)
    assert late["focus"] != "go_hard" or late["block"] is None


def test_hard_day_is_blocked_by_any_warning_sign():
    for sig in ({"load": dict(ratio=0.7, consecutive_hard_days=2, level="low")},
                {"load": dict(ratio=1.2, consecutive_hard_days=0, level="normal")},
                {"load": dict(ratio=0.7, consecutive_hard_days=0, level="low"), "hrv": dict(status="below",
                 recent_mean=48, normal_low=55, normal_high=61)}):
        f = choose_focus(summary(zone="green", recovery=82, rec_status="better", signals=sig), EMPTY, TODAY)
        assert f["focus"] != "go_hard"


def test_same_focus_three_days_running_needs_stronger_evidence():
    sig = {"load": dict(ratio=1.45, consecutive_hard_days=0, level="high")}  # moderate evidence (0.55)
    first = choose_focus(summary(signals=sig), EMPTY, TODAY)
    assert first["focus"] == "lower_intensity"
    again = choose_focus(summary(signals=sig), EMPTY, TODAY, recent_focuses=["lower_intensity"] * 2)
    assert again["focus"] == "none"
    once = choose_focus(summary(signals=sig), EMPTY, TODAY, recent_focuses=["lower_intensity", "none"])
    assert once["focus"] == "lower_intensity"


def test_marked_not_useful_needs_stronger_evidence_but_silence_does_not():
    sig = {"load": dict(ratio=1.45, consecutive_hard_days=0, level="high")}  # moderate evidence
    muted = choose_focus(summary(signals=sig), EMPTY, TODAY, not_useful={"lower_intensity"})
    assert muted["focus"] == "none"
    strong = {"load": dict(ratio=1.6, consecutive_hard_days=3, level="very_high")}
    assert choose_focus(summary(signals=strong), EMPTY, TODAY, not_useful={"lower_intensity"})["focus"] \
        == "lower_intensity"


def test_busy_day_while_strained_suggests_a_break():
    sig = {"load": NORMAL_LOAD}
    f = choose_focus(summary(zone="yellow", busy_hours=9, meetings=7, signals=sig,
                             free=[dict(start="13:00", end="13:30", minutes=30)]), EMPTY, TODAY)
    assert f["focus"] == "recover_between" and f["block"]["start"] == "13:00"


def test_waits_when_last_night_is_not_scored():
    f = choose_focus(summary(scored=False), EMPTY, TODAY)
    assert f["focus"] == "none" and "Waiting" in f["title"]


def test_find_slot_prefers_late_afternoon_and_respects_latest_end():
    free = [dict(start="09:00", end="11:00", minutes=120), dict(start="15:00", end="20:00", minutes=300)]
    assert find_slot(free, 60)["start"] == "16:00"
    assert find_slot(free, 60, latest_end=16 * 60 + 30)["start"] == "09:00"
    assert find_slot([dict(start="09:00", end="09:20", minutes=20)], 30) is None


def test_usual_bedtime_handles_midnight():
    days = [TODAY - timedelta(days=k) for k in range(1, 8)]
    starts = [datetime(d.year, d.month, d.day, 23, 30) if i % 2 else
              datetime(d.year, d.month, d.day, 23, 59) + timedelta(minutes=31) for i, d in enumerate(days)]
    panel = pd.DataFrame({"sleep_start_local": starts}, index=pd.Index(days, name="day"))
    bt = usual_bedtime(panel, TODAY)
    assert 23 * 60 + 30 <= bt <= 24 * 60 + 30


def test_advice_states_confidence_counter_evidence_and_why_not_hard():
    sig = {"load": dict(ratio=1.55, consecutive_hard_days=3, level="very_high"),
           "hrv": dict(status="below", recent_mean=48, normal_low=55, normal_high=61),
           "resting_hr": dict(status="within", recent_mean=55, normal_low=54, normal_high=56)}
    s = summary(signals=sig)
    s["metrics"].append(dict(key="sleep_performance_pct", value=85, status="typical", delta=0))
    f = choose_focus(s, EMPTY, TODAY)
    assert f["focus"] == "lower_intensity" and f["confidence"] in ("high", "moderate", "tentative")
    assert f["headline"] and f["caveat"]
    assert any("resting heart rate is within" in c for c in f["counter"])
    assert any("sleep performance was 85%" in c for c in f["counter"])
    why_not = " ".join(f["alternatives"])
    assert "Not a hard session today" in why_not and "HRV is below" in why_not and "3 hard days" in why_not


def test_confidence_bands():
    from src.planner.focus import confidence
    assert confidence(0.8) == "high" and confidence(0.65) == "moderate" and confidence(0.5) == "tentative"
