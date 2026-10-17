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
    assert f["schedulable"] is True    # the easy walk can go on the calendar, optionally


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


def test_find_slot_stays_close_to_the_preferred_time_and_respects_latest_end():
    free = [dict(start="09:00", end="11:00", minutes=120), dict(start="15:00", end="20:00", minutes=300)]
    assert find_slot(free, 60)["start"] == "16:00"
    assert find_slot(free, 60, latest_end=16 * 60 + 30)["start"] == "15:30"   # as close to 16:00 as fits
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


def test_planner_uses_your_activity_at_your_usual_time():
    from src.planner.habits import activity_profile
    from tests.test_habits import workout
    habits = activity_profile([workout(d, "running", 14, 50, 12.0) for d in (2, 5, 9, 12)], date(2026, 10, 17))
    sig = {"load": dict(ratio=1.55, consecutive_hard_days=3, level="very_high")}
    free = [dict(start="07:00", end="09:00", minutes=120), dict(start="12:00", end="24:00", minutes=720)]
    f = choose_focus(summary(signals=sig, free=free), EMPTY, TODAY, habits=habits)
    assert f["focus"] == "lower_intensity" and f["block"]["start"] == "07:00"     # you usually run at 07:00
    assert f["block"]["title"].startswith("Easy running") and "last 8 weeks" in f["note"]


def test_todays_case_hard_yesterday_low_hrv_and_chronic_sleep_debt():
    """Oct 17: HRV below range, resting HR above, strain 15.5 yesterday, 9h45m short over 7 nights."""
    sig = {"load": dict(ratio=1.2, consecutive_hard_days=1, level="normal", yesterday_load=15.5),
           "hrv": dict(status="below", recent_mean=95.2, normal_low=97.7, normal_high=117.5),
           "resting_hr": dict(status="above", recent_mean=56),
           "sleep": dict(shortfall_min=585, typical_shortfall_min=560, nights_measured=7, nights_short=6,
                         need_source="whoop")}
    f = choose_focus(summary(signals=sig, sleep_delta=-45), EMPTY, TODAY)
    assert f["focus"] == "lower_intensity" and f["confidence"] in ("moderate", "high")
    assert any("strain 15.5" in r for r in f["reasons"]) and any("behind on sleep" in r for r in f["reasons"])
    # chronic sleep debt now counts even though it is "your usual week"
    sleep_score = dict(f["considered"])["prioritize_sleep"]
    assert sleep_score >= THRESHOLD


def test_slots_start_on_the_quarter_hour():
    assert find_slot([dict(start="15:16", end="24:00", minutes=524)], 30, prefer=(19 * 60 - 1, 20 * 60))["start"] \
        == "19:00"
    assert find_slot([dict(start="15:16", end="16:00", minutes=44)], 30, prefer=None)["start"] == "15:30"


def test_walks_go_into_free_afternoon_time_and_never_late():
    sig = {"load": dict(ratio=1.55, consecutive_hard_days=3, level="very_high")}
    late_only = [dict(start="20:00", end="24:00", minutes=240)]
    f = choose_focus(summary(signals=sig, free=late_only), EMPTY, TODAY)
    assert f["focus"] == "lower_intensity" and f["block"] is None             # nothing before 20:00: no walk
    f = choose_focus(summary(signals=sig, free=[dict(start="13:00", end="24:00", minutes=660)]), EMPTY, TODAY)
    assert f["block"]["start"] == "16:00" and f["block"]["end"] == "16:30"
