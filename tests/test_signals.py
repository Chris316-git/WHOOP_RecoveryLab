from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.report.signals import (
    compute_signals,
    sleep_shortfall,
    training_load,
    vital_trend,
    weekday_pattern,
)
from src.sources.whoop import sleep_need_minutes

TODAY = date(2026, 10, 16)  # a Friday


def make_panel(days=60, **cols):
    idx = [TODAY - timedelta(days=k) for k in range(days, 0, -1)]
    rng = np.random.default_rng(0)
    data = {
        "hrv_rmssd_milli": 60 + rng.normal(0, 3, days),
        "resting_heart_rate": 55 + rng.normal(0, 1, days),
        "total_sleep_min": 450 + rng.normal(0, 15, days),
        "load": 10 + rng.normal(0, 1, days),
    }
    data.update(cols)
    return pd.DataFrame(data, index=pd.Index(idx, name="day"))


def test_hrv_drop_in_last_week_is_below_normal_range():
    p = make_panel()
    p.loc[p.index >= TODAY - timedelta(days=7), "hrv_rmssd_milli"] = 45.0
    t = vital_trend(p, TODAY, "hrv_rmssd_milli", log_scale=True)
    assert t["status"] == "below" and t["recent_mean"] == 45.0
    assert t["normal_low"] < 60 < t["normal_high"]
    assert vital_trend(make_panel(), TODAY, "resting_heart_rate")["status"] in ("within", "below", "above")


def test_not_enough_history_returns_none():
    assert vital_trend(make_panel(days=10), TODAY, "hrv_rmssd_milli") is None
    assert training_load(make_panel(days=10), TODAY) is None


def test_sleep_shortfall_uses_whoop_need_or_default():
    p = make_panel(total_sleep_min=[420.0] * 60)
    s = sleep_shortfall(p, TODAY)
    assert s["need_source"] == "default_8h" and s["shortfall_min"] == 7 * 60
    p["sleep_need_baseline_min"] = 450.0
    s = sleep_shortfall(p, TODAY)
    assert s["need_source"] == "whoop" and s["shortfall_min"] == 7 * 30 and s["nights_short"] == 7


def test_training_load_ratio_and_hard_streak():
    p = make_panel(strain=[10.0] * 60)
    p.loc[p.index >= TODAY - timedelta(days=3), "load"] = 16.0
    load = training_load(p, TODAY)
    assert load["consecutive_hard_days"] == 3
    assert load["ratio"] > 1.0 and load["yesterday_load"] == 16.0


def test_weekday_pattern_only_when_reliable():
    p = make_panel(total_sleep_min=[460.0] * 60)
    assert weekday_pattern(p, TODAY) is None
    fridays = [d for d in p.index if d.weekday() == TODAY.weekday()]
    p.loc[fridays, "total_sleep_min"] = 400.0
    wd = weekday_pattern(p, TODAY)
    assert wd["weekday"] == "Friday" and wd["gap_min"] == -60


def test_compute_signals_and_sleep_need_parsing():
    sig = compute_signals(make_panel(), TODAY)
    assert set(sig) == {"hrv_daily", "hrv", "resting_hr", "sleep", "load", "weekday"}
    raw = {"score": {"sleep_needed": {"baseline_milli": 27_000_000, "need_from_sleep_debt_milli": 1_800_000,
                                      "need_from_recent_strain_milli": 600_000,
                                      "need_from_recent_nap_milli": -1_200_000}}}
    assert sleep_need_minutes(raw) == (450.0, 470.0)
    assert sleep_need_minutes({"score": {}}) == (None, None)
