"""Monte Carlo checks of the experiment analysis on synthetic, autocorrelated nights.

Nightly outcomes follow an AR(1) process (a good night tends to follow a good night, as with
real sleep), the schedule is the real randomized paired design, and the analysis is the real
one from analysis.py. Used by the tests and by the demo page. Pure logic.
"""
import random
from datetime import date

from src.experiments.analysis import pair_differences, randomization_p, summarize, t_interval
from src.experiments.design import make_schedule

START = date(2026, 1, 5)


def simulate_nights(effect: float, rng: random.Random, pairs: int = 7, phi: float = 0.5, sd: float = 6.0,
                    base: float = 78.0) -> list[dict]:
    sched = make_schedule(START, 2 * pairs, seed=rng.randrange(10**9))
    x, nights = 0.0, []
    for s in sched:
        x = phi * x + rng.gauss(0, sd * (1 - phi ** 2) ** 0.5)
        nights.append(dict(s, y=base + x + (effect if s["arm"] == "treatment" else 0)))
    return nights


def simulate(effect: float, rng: random.Random, pairs: int = 7, phi: float = 0.5, sd: float = 6.0) -> list[float]:
    """Pair differences of one simulated experiment."""
    return pair_differences(simulate_nights(effect, rng, pairs, phi, sd), "y")


def calibration(sims: int = 2000, pairs: int = 7, seed: int = 42) -> dict:
    """With no true effect: how often a 'clear' result appears (should be about 5%), and how
    often the 95% interval contains the true effect (should be about 95%)."""
    rng = random.Random(seed)
    false_pos = cover = 0
    for _ in range(sims):
        d = simulate(0.0, rng, pairs)
        false_pos += randomization_p(d) < 0.05
        lo, hi = t_interval(d)
        cover += lo <= 0.0 <= hi
    return dict(sims=sims, pairs=pairs, false_positive_rate=false_pos / sims, coverage=cover / sims)


def power(effects: tuple[float, ...] = (3.0, 5.0, 8.0), nights: tuple[int, ...] = (14, 20), sims: int = 800,
          meaningful: float = 3.0, seed: int = 7) -> list[dict]:
    """Share of simulated experiments that end with "helped" for each true effect and length."""
    rng = random.Random(seed)
    rows = []
    for n in nights:
        row = dict(nights=n)
        for e in effects:
            hits = sum(summarize(simulate(e, rng, n // 2), meaningful)["verdict"] == "helped" for _ in range(sims))
            row[e] = hits / sims
        rows.append(row)
    return rows
