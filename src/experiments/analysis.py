"""Analysis of a paired, randomized N-of-1 experiment. Pure logic, no modelling assumptions
beyond the randomization itself.

* Unit of analysis: a pair of nights, one treatment and one control, order randomized.
  The pair difference (treatment minus control) removes slow drifts shared by both nights.
* Effect: the mean pair difference.
* p-value: a randomization test. Under "the habit makes no difference" each pair difference
  is equally likely to have either sign, so we compare the observed mean with all 2^n sign
  flips (exact up to 16 pairs, Monte Carlo above). Its validity rests only on the coin flips.
* Interval: a 95% t-interval on the pair differences (small-sample honest; checked by
  simulation in tests/test_experiments.py).
* Two views: intention-to-treat (all pairs, as assigned; the primary result) and
  per-protocol (only pairs whose treatment night you confirmed).
* Verdict, pre-specified: "helped" / "worse" need a clear interval and p < 0.05;
  "no meaningful effect" needs the whole interval inside +/- the preset's smallest
  meaningful effect; everything else is "inconclusive"; fewer than MIN_PAIRS pairs is
  "not enough data". One person's experiment says nothing about other people.
"""
import math
import random
from itertools import product

MIN_PAIRS = 6   # with 5 pairs the smallest possible two-sided randomization p is 2/32 > 0.05
ALPHA = 0.05
MC_DRAWS = 20000
# Two-sided 97.5% quantiles of Student's t for df 1..30 (beyond 30, 1.96 is close enough).
T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def pair_differences(nights: list[dict], column: str, per_protocol: bool = False) -> list[float]:
    """nights: [{"pair", "arm", "adherence", column: value}, ...] -> treatment minus control per pair."""
    pairs: dict[int, dict] = {}
    for n in nights:
        pairs.setdefault(n["pair"], {})[n["arm"]] = n
    out = []
    for p in sorted(pairs):
        t, c = pairs[p].get("treatment"), pairs[p].get("control")
        if not t or not c or t.get(column) is None or c.get(column) is None:
            continue
        if per_protocol and t.get("adherence") != "yes":
            continue
        out.append(float(t[column]) - float(c[column]))
    return out


def randomization_p(diffs: list[float], seed: int = 0) -> float:
    n = len(diffs)
    observed = abs(sum(diffs) / n)
    if n <= 16:
        signs = product((1, -1), repeat=n)
        total = extreme = 0
        for s in signs:
            total += 1
            extreme += abs(sum(a * b for a, b in zip(s, diffs)) / n) >= observed - 1e-12
        return extreme / total
    rng = random.Random(seed)
    extreme = sum(abs(sum(d if rng.random() < 0.5 else -d for d in diffs) / n) >= observed - 1e-12
                  for _ in range(MC_DRAWS))
    return (extreme + 1) / (MC_DRAWS + 1)


def t_interval(diffs: list[float]) -> tuple[float, float]:
    n = len(diffs)
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1))
    q = T975[n - 2] if n - 1 <= len(T975) else 1.96
    half = q * sd / math.sqrt(n)
    return mean - half, mean + half


def summarize(diffs: list[float], meaningful: float) -> dict:
    n = len(diffs)
    if n < MIN_PAIRS:
        return dict(pairs=n, verdict="not_enough_data", effect=None, ci=None, p=None)
    effect = sum(diffs) / n
    lo, hi = t_interval(diffs)
    p = randomization_p(diffs)
    if lo > 0 and p < ALPHA:
        verdict = "helped"
    elif hi < 0 and p < ALPHA:
        verdict = "worse"
    elif -meaningful < lo and hi < meaningful:
        verdict = "no_meaningful_effect"
    else:
        verdict = "inconclusive"
    return dict(pairs=n, verdict=verdict, effect=round(effect, 1), ci=[round(lo, 1), round(hi, 1)], p=round(p, 3))


def analyze(nights: list[dict], spec: dict) -> dict:
    """Full result for a preset spec (see presets.py)."""
    out, sec = spec["outcome"], spec["secondary"]
    treatment = [n for n in nights if n["arm"] == "treatment"]
    confirmed = sum(n.get("adherence") == "yes" for n in treatment)
    answered = sum(n.get("adherence") in ("yes", "no") for n in treatment)
    return dict(
        primary=dict(label=out["label"], unit=out["unit"], meaningful=out["meaningful"],
                     itt=summarize(pair_differences(nights, out["column"]), out["meaningful"]),
                     per_protocol=summarize(pair_differences(nights, out["column"], True), out["meaningful"])),
        secondary=dict(label=sec["label"], unit=sec["unit"],
                       itt=summarize(pair_differences(nights, sec["column"]), sec["meaningful"])),
        adherence=dict(treatment_nights=len(treatment), confirmed=confirmed, answered=answered),
    )


VERDICT_TEXT = {
    "helped": "On {short} nights your {label} was clearly higher.",
    "worse": "On {short} nights your {label} was clearly lower.",
    "no_meaningful_effect": ("The habit made no meaningful difference to your {label} "
                             "(less than {m:g} {unit} either way)."),
    "inconclusive": "The data cannot tell yet whether the habit helps your {label}.",
    "not_enough_data": "Not enough complete pairs of nights to judge the effect on your {label}.",
}


def explain(result: dict, spec: dict) -> str:
    """Plain-language summary built only from computed numbers."""
    p = result["primary"]
    r = p["itt"]
    text = VERDICT_TEXT[r["verdict"]].format(label=p["label"].lower(), m=p["meaningful"], unit=p["unit"],
                                             short=spec["short"])
    if r["effect"] is not None:
        text += (f" Difference: {r['effect']:+g} {p['unit']} (95% interval {r['ci'][0]:+g} to {r['ci'][1]:+g}), "
                 f"{r['pairs']} pairs of nights, randomization test p = {r['p']:g}.")
    a = result["adherence"]
    text += f" You confirmed {a['confirmed']} of {a['treatment_nights']} {spec['short']} nights."
    if a["treatment_nights"] and a["confirmed"] / a["treatment_nights"] < 0.6:
        text += " With that many missed nights, the result says more about the plan than about the habit itself."
    return text
