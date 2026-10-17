import random
from datetime import date

from src.experiments.analysis import analyze, explain, pair_differences, randomization_p, summarize, t_interval
from src.experiments.design import arm_on, make_schedule
from src.experiments.presets import preset

START = date(2026, 10, 18)


def test_schedule_is_balanced_paired_and_reproducible():
    s = make_schedule(START, 14, seed=7)
    assert len(s) == 14 and s == make_schedule(START, 14, seed=7)
    for p in range(7):
        assert sorted(x["arm"] for x in s if x["pair"] == p) == ["control", "treatment"]
    assert arm_on(s, START)["day"] == "2026-10-18" and arm_on(s, date(2026, 11, 30)) is None


def test_exact_randomization_test():
    assert randomization_p([1.0, 1.0, 1.0, 1.0, 1.0]) == 2 / 32          # only all-plus or all-minus as extreme
    lo, hi = t_interval([1.0, 2.0, 3.0, 4.0, 5.0])
    assert round(lo, 2) == 1.04 and round(hi, 2) == 4.96


def test_verdicts():
    assert summarize([1, 2], 3)["verdict"] == "not_enough_data"
    assert summarize([6, 7, 5, 8, 6, 7, 6], 3)["verdict"] == "helped"
    assert summarize([0.2, -0.3, 0.1, -0.1, 0.0, 0.2, -0.2], 3)["verdict"] == "no_meaningful_effect"
    assert summarize([5, -6, 4, -3, 7, -5, 2], 3)["verdict"] == "inconclusive"


def test_pairs_and_per_protocol():
    nights = [dict(pair=0, arm="treatment", adherence="yes", y=80), dict(pair=0, arm="control", y=75),
              dict(pair=1, arm="treatment", adherence="no", y=70), dict(pair=1, arm="control", y=72),
              dict(pair=2, arm="treatment", adherence=None, y=None), dict(pair=2, arm="control", y=70)]
    assert pair_differences(nights, "y") == [5.0, -2.0]
    assert pair_differences(nights, "y", per_protocol=True) == [5.0]


def simulate(effect, rng, pairs=7, phi=0.5, sd=6.0):
    """AR(1) nightly outcomes (autocorrelated, like real sleep), randomized paired schedule."""
    sched = make_schedule(START, 2 * pairs, seed=rng.randrange(10**9))
    x, nights = 0.0, []
    for s in sched:
        x = phi * x + rng.gauss(0, sd * (1 - phi ** 2) ** 0.5)
        nights.append(dict(s, y=78 + x + (effect if s["arm"] == "treatment" else 0)))
    return pair_differences(nights, "y")


def test_simulation_false_positives_and_coverage():
    """With no true effect, "helped"/"worse" should be rare (about 5%), and the 95% interval
    should contain the true effect about 95% of the time, even with autocorrelated nights."""
    rng = random.Random(42)
    sims = 400
    false_pos = cover = 0
    for _ in range(sims):
        d = simulate(0.0, rng)
        false_pos += randomization_p(d) < 0.05
        lo, hi = t_interval(d)
        cover += lo <= 0.0 <= hi
    assert false_pos / sims <= 0.08
    assert cover / sims >= 0.90
    hits = sum(summarize(simulate(8.0, rng), 3)["verdict"] == "helped" for _ in range(100))
    assert hits >= 60                                                    # a large real effect is usually found


def test_full_analysis_and_explanation():
    spec = preset("screens_off_30")
    sched = make_schedule(START, 14, seed=1)
    nights = [dict(s, adherence="yes" if s["arm"] == "treatment" else None,
                   sleep_performance_pct=80 + (5 if s["arm"] == "treatment" else 0) + (i % 3),
                   hrv_rmssd_milli=100.0) for i, s in enumerate(sched)]
    r = analyze(nights, spec)
    assert r["primary"]["itt"]["pairs"] == 7 and r["adherence"]["confirmed"] == 7
    text = explain(r, spec)
    assert "screen-free" in text and "randomization test" in text


def _panel(days, perf=80.0):
    import pandas as pd
    return pd.DataFrame({"sleep_performance_pct": [perf] * len(days), "hrv_rmssd_milli": [100.0] * len(days),
                         "sleep_start_local": [pd.Timestamp(f"{d.isoformat()} 23:40") for d in days]},
                        index=pd.Index(days, name="day"))


def test_email_info_tonight_ask_and_result():
    from datetime import timedelta

    from src.experiments.daily import experiment_today
    sched = make_schedule(START, 4, seed=3)
    exp = dict(id=1, preset="screens_off_30", nights=4, schedule=sched)
    first_t = next(s for s in sched if s["arm"] == "treatment")
    day_after = date.fromisoformat(first_t["day"]) + timedelta(days=1)
    info = experiment_today(exp, {}, _panel([START + timedelta(days=k) for k in range(4)]), day_after, 23 * 60 + 30)
    assert info["ask"]["day"] == first_t["day"] and "23:40" in info["ask"]["hint"]
    if info.get("arm") == "treatment":
        assert "screens off from 23:00" in info["tonight"]
    answered = experiment_today(exp, {first_t["day"]: "yes"}, _panel([START]), day_after, None)
    assert "ask" not in answered
    after = START + timedelta(days=4)
    days = [START + timedelta(days=k) for k in range(4)]
    answers = {s["day"]: "yes" for s in sched if s["arm"] == "treatment"}
    done = experiment_today(exp, answers, _panel(days), after + timedelta(days=1), None)
    assert done["done"] and done["result"]["primary"]["itt"]["verdict"] == "not_enough_data"   # only 2 pairs
