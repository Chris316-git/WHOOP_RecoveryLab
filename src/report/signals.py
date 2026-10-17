"""Personal trend signals for the morning report and, later, the daily planner. Pure logic.

All comparisons are against the user's OWN history:

* HRV and resting heart rate: the last 7 days vs. a "normal range" built from the 30 days
  before them (mean ± 0.5 SD). HRV is compared on the log scale (ln RMSSD), as is common
  practice, because its day-to-day spread grows with its level.
* Sleep shortfall: the last 7 nights vs. WHOOP's baseline sleep need (falls back to 8 h,
  and says so, when the need is unavailable).
* Training load: the mean daily load (WHOOP strain scale) of the last 7 days vs. the last 28 days (an
  acute:chronic ratio), plus the number of consecutive hard days. This is a heuristic for
  "more or less than you are used to", not an injury predictor.
* Weekday pattern: whether tonight's weekday is reliably a short-sleep night for you.

Day convention (see src/analysis/panel.py): row `d` holds the sleep that starts on the
night of `d` and the load of day `d`. On the morning of `today`, the latest complete row
is `today - 1`.
"""
import math
from datetime import date, timedelta

import pandas as pd

RECENT_DAYS = 7
BASELINE_DAYS = 30
MIN_RECENT = 4
MIN_BASELINE = 14
NORMAL_BAND_SD = 0.5

LOAD_ACUTE_DAYS = 7
LOAD_CHRONIC_DAYS = 28
MIN_LOAD_DAYS = 21
HARD_STRAIN = 14.0          # WHOOP's "strenuous" band starts at 14

FALLBACK_SLEEP_NEED_MIN = 480
WEEKDAY_LOOKBACK_DAYS = 56
WEEKDAY_MIN_NIGHTS = 4
WEEKDAY_MIN_GAP_MIN = 30
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _window(panel: pd.DataFrame, col: str, start: date, end: date) -> pd.Series:
    """Values of `col` for days in [start, end)."""
    if col not in panel or not len(panel):
        return pd.Series(dtype=float)
    mask = (panel.index >= start) & (panel.index < end)
    return pd.to_numeric(panel.loc[mask, col], errors="coerce").dropna()


def vital_trend(panel: pd.DataFrame, today: date, col: str, log_scale: bool = False,
                min_half_width: float = 0.0) -> dict | None:
    """Last-7-day mean vs. the normal range of the 30 days before that.

    `min_half_width` (in the compared scale) keeps the range from becoming so narrow that
    trivial changes get flagged when the baseline happens to be very stable.
    """
    recent_start = today - timedelta(days=RECENT_DAYS)
    base_start = recent_start - timedelta(days=BASELINE_DAYS)
    recent = _window(panel, col, recent_start, today)
    base = _window(panel, col, base_start, recent_start)
    if log_scale:
        recent, base = recent[recent > 0].map(math.log), base[base > 0].map(math.log)
    if len(recent) < MIN_RECENT or len(base) < MIN_BASELINE:
        return None
    back = math.exp if log_scale else float
    mean, sd = float(base.mean()), float(base.std(ddof=1))
    half = max(NORMAL_BAND_SD * sd, min_half_width)
    lo, hi = mean - half, mean + half
    recent_mean = float(recent.mean())
    return dict(
        recent_mean=round(back(recent_mean), 1),
        normal_low=round(back(lo), 1),
        normal_high=round(back(hi), 1),
        # Position relative to the normal range; whether that is good depends on the metric.
        status="below" if recent_mean < lo else "above" if recent_mean > hi else "within",
        recent_days=int(len(recent)),
        baseline_days=int(len(base)),
    )


def sleep_shortfall(panel: pd.DataFrame, today: date) -> dict | None:
    """Total shortfall vs. sleep need over the last 7 nights (surplus nights count as 0)."""
    start = today - timedelta(days=RECENT_DAYS)
    sleep = _window(panel, "total_sleep_min", start, today)
    if len(sleep) < MIN_RECENT:
        return None
    need_series = _window(panel, "sleep_need_baseline_min", today - timedelta(days=BASELINE_DAYS), today)
    need = float(need_series.median()) if len(need_series) else float(FALLBACK_SLEEP_NEED_MIN)
    short = (need - sleep).clip(lower=0)

    # Your typical 7-night shortfall over the previous 30 days, so a chronically short
    # sleeper is not told "sleep more" every single day: what stands out is a week that is
    # worse than YOUR usual (plus a large absolute shortfall, reported separately).
    history = (need - _window(panel, "total_sleep_min", start - timedelta(days=BASELINE_DAYS), start)).clip(lower=0)
    weekly = []
    for end in history.index:
        win = history[(history.index > end - timedelta(days=RECENT_DAYS)) & (history.index <= end)]
        if len(win) >= MIN_RECENT:
            weekly.append(float(win.mean()) * RECENT_DAYS)
    typical = round(float(pd.Series(weekly).median())) if len(weekly) >= 7 else None
    return dict(
        shortfall_min=round(float(short.sum())),
        typical_shortfall_min=typical,
        nights_measured=int(len(sleep)),
        nights_short=int((short >= 30).sum()),
        avg_sleep_min=round(float(sleep.mean())),
        need_min=round(need),
        need_source="whoop" if len(need_series) else "default_8h",
    )


def training_load(panel: pd.DataFrame, today: date) -> dict | None:
    """Acute (7-day) vs chronic (28-day) mean strain, and consecutive hard days up to yesterday."""
    chronic = _window(panel, "load", today - timedelta(days=LOAD_CHRONIC_DAYS), today)
    acute = _window(panel, "load", today - timedelta(days=LOAD_ACUTE_DAYS), today)
    if len(chronic) < MIN_LOAD_DAYS or len(acute) < MIN_RECENT or chronic.mean() <= 0:
        return None
    ratio = float(acute.mean() / chronic.mean())
    level = ("low" if ratio < 0.8 else "normal" if ratio <= 1.3 else "high" if ratio <= 1.5 else "very_high")
    streak, d = 0, today - timedelta(days=1)
    strain = panel["load"] if "load" in panel else pd.Series(dtype=float)
    while d in strain.index and pd.notna(strain.loc[d]) and float(strain.loc[d]) >= HARD_STRAIN:
        streak += 1
        d -= timedelta(days=1)
    yesterday = strain.get(today - timedelta(days=1)) if len(strain) else None
    return dict(
        acute_mean=round(float(acute.mean()), 1),
        chronic_mean=round(float(chronic.mean()), 1),
        ratio=round(ratio, 2),
        level=level,
        consecutive_hard_days=streak,
        yesterday_load=None if yesterday is None or pd.isna(yesterday) else round(float(yesterday), 1),
    )


def weekday_pattern(panel: pd.DataFrame, today: date) -> dict | None:
    """Is tonight's weekday reliably a short-sleep night? Mentioned only when it is."""
    sleep = _window(panel, "total_sleep_min", today - timedelta(days=WEEKDAY_LOOKBACK_DAYS), today)
    if len(sleep) < 4 * 7:
        return None
    same_day = sleep[[d.weekday() == today.weekday() for d in sleep.index]]
    if len(same_day) < WEEKDAY_MIN_NIGHTS:
        return None
    others = sleep[[d.weekday() != today.weekday() for d in sleep.index]]
    gap = float(same_day.mean() - others.mean())
    consistent = float((same_day < others.median()).mean())  # share of these nights below your usual
    if gap > -WEEKDAY_MIN_GAP_MIN or consistent < 0.75:
        return None
    return dict(
        weekday=WEEKDAY_NAMES[today.weekday()],
        gap_min=round(gap),
        nights=int(len(same_day)),
        share_below_usual=round(consistent, 2),
    )


def compute_signals(panel: pd.DataFrame, today: date) -> dict:
    return dict(
        hrv=vital_trend(panel, today, "hrv_rmssd_milli", log_scale=True, min_half_width=0.03),  # about ±3%
        resting_hr=vital_trend(panel, today, "resting_heart_rate", min_half_width=1.0),         # ±1 bpm
        sleep=sleep_shortfall(panel, today),
        load=training_load(panel, today),
        weekday=weekday_pattern(panel, today),
    )
