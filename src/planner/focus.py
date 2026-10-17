"""Pick ONE focus for today, or decide that nothing needs to change. Pure logic, no I/O.

How it works:

1. Each candidate focus looks at the morning signals (src/report/signals.py), last night's
   metrics and today's calendar, and collects *triggers*. Each trigger has a strength in
   [0, 1] and a plain-language reason built from the numbers.
2. A candidate's evidence combines its triggers like independent pieces of evidence
   (1 - Π(1 - s)), so several moderate signals add up but never exceed 1.
3. Its score is evidence × actionability (can the user act on it today, e.g. is there a
   suitable free slot?).
4. The best candidate is chosen only if its score clears THRESHOLD; otherwise the plan is
   "nothing needs to change". Ties follow PRIORITY (protective focuses first).

The thresholds below are starting values meant to be tuned with real use (and, later,
with the feedback loop and experiments). They are rules of thumb, not medical advice.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

THRESHOLD = 0.45
PRIORITY = ["lower_intensity", "prioritize_sleep", "recover_between", "go_hard"]

HARD_MIN_BEFORE_BED = 180      # hard sessions end at least 3 h before the target bedtime
EASY_MIN_BEFORE_BED = 60
PREFERRED_START, PREFERRED_END = 16 * 60, 19 * 60   # late afternoon, used to break ties
DEFAULT_BEDTIME = 23 * 60
EARLIEST_TARGET_BEDTIME = 21 * 60 + 30
WIND_DOWN_MIN = 45
BEDTIME_HISTORY_DAYS = 14

TITLES = {
    "lower_intensity": "Take it easy today",
    "prioritize_sleep": "Protect your sleep tonight",
    "recover_between": "Build breaks into a busy day",
    "go_hard": "Good day for a hard session",
    "none": "Nothing needs to change today",
}


@dataclass
class Candidate:
    key: str
    triggers: list[tuple[float, str]] = field(default_factory=list)
    actionability: float = 1.0
    block: dict | None = None
    note: str | None = None

    def add(self, strength: float, reason: str) -> None:
        if strength > 0:
            self.triggers.append((min(1.0, strength), reason))

    @property
    def evidence(self) -> float:
        p = 1.0
        for s, _ in self.triggers:
            p *= 1 - s
        return 1 - p

    @property
    def score(self) -> float:
        return round(self.evidence * self.actionability, 3)


# ---------------- time helpers ----------------

def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: float) -> str:
    minutes = int(round(minutes)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def usual_bedtime(panel: pd.DataFrame, today: date) -> int | None:
    """Median local sleep start over the last two weeks, in minutes after midnight
    (values after midnight are > 1440 so that 23:30 and 00:30 average sensibly)."""
    if "sleep_start_local" not in panel or not len(panel):
        return None
    lo = today - timedelta(days=BEDTIME_HISTORY_DAYS)
    starts = panel.loc[(panel.index >= lo) & (panel.index < today), "sleep_start_local"].dropna()
    mins = []
    for t in starts:
        t = pd.Timestamp(t)
        m = t.hour * 60 + t.minute
        mins.append(m + 1440 if m < 12 * 60 else m)
    return int(pd.Series(mins).median()) if len(mins) >= 5 else None


def find_slot(free_windows: list[dict], minutes: int, latest_end: int | None = None,
              prefer: tuple[int, int] | None = (PREFERRED_START, PREFERRED_END)) -> dict | None:
    """A slot of `minutes` inside a free window, ending by `latest_end` (minutes after midnight).

    Prefers a start inside `prefer`; otherwise the earliest start that fits.
    """
    options = []
    for w in free_windows:
        s, e = _to_min(w["start"]), _to_min(w["end"])
        if latest_end is not None:
            e = min(e, latest_end)
        if e - s < minutes:
            continue
        start = s
        if prefer and s < prefer[0] <= e - minutes:
            start = prefer[0]
        options.append(start)
    if not options:
        return None
    inside = [o for o in options if prefer and prefer[0] <= o <= prefer[1]]
    start = min(inside) if inside else min(options)
    return dict(start=_to_hhmm(start), end=_to_hhmm(start + minutes), minutes=minutes)


# ---------------- candidates ----------------

def _metric(summary: dict, key: str) -> dict:
    return next((m for m in summary["metrics"] if m["key"] == key), {})


def _lower_intensity(summary: dict, sig: dict, free: list[dict], bedtime: int) -> Candidate:
    c = Candidate("lower_intensity")
    load, hrv, rhr = sig.get("load"), sig.get("hrv"), sig.get("resting_hr")
    if summary["recovery_zone"] == "red":
        c.add(0.6, f"recovery is {summary['metrics'][0]['value']:g}%, in the red zone")
    if load:
        if load["ratio"] > 1.3:
            c.add(min(1.0, (load["ratio"] - 1.3) / 0.3 * 0.5 + 0.3),
                  f"training load is {load['ratio']:g}x your 4-week average")
        if load["consecutive_hard_days"] >= 2:
            c.add(0.2 * load["consecutive_hard_days"], f"{load['consecutive_hard_days']} hard days in a row")
    if hrv and hrv["status"] == "below":
        c.add(0.4, f"HRV has been below your normal range this week ({hrv['recent_mean']:g} ms "
                   f"vs {hrv['normal_low']:g}-{hrv['normal_high']:g})")
    if rhr and rhr["status"] == "above":
        c.add(0.3, f"resting heart rate is above your normal range this week ({rhr['recent_mean']:g} bpm)")
    if _metric(summary, "hrv_rmssd_milli").get("status") == "worse":
        c.add(0.2, "last night's HRV was low for you")
    c.block = find_slot(free, 30, latest_end=bedtime - EASY_MIN_BEFORE_BED)
    if c.block:
        c.block["title"] = "Easy movement: walk or mobility"
    return c


def _prioritize_sleep(summary: dict, sig: dict, bedtime: int, target_bedtime: int) -> Candidate:
    c = Candidate("prioritize_sleep")
    sleep, wd = sig.get("sleep"), sig.get("weekday")
    if sleep:
        short, typical = sleep["shortfall_min"], sleep.get("typical_shortfall_min")
        short7 = short / max(1, sleep["nights_measured"]) * 7   # comparable to a full week
        assumed = sleep.get("need_source") != "whoop"
        weight = 0.6 if assumed else 1.0      # less confident when the 8 h need is only assumed
        text = (f"{short // 60}h {short % 60:02d}m short of your sleep need over the last "
                f"{sleep['nights_measured']} nights")
        if typical is not None:
            excess = short7 - typical
            if excess >= 60:
                c.add(weight * min(1.0, 0.3 + excess / 240 * 0.5), f"you are {text}, more than your usual week")
        elif short7 >= 120:
            c.add(weight * min(1.0, 0.3 + (short7 - 120) / 240 * 0.5), f"you are {text}")
        if short7 >= 7 * 60:  # about an hour short per night on average
            c.add(weight * 0.3, "you have averaged about an hour or more below your need per night")
    last = _metric(summary, "total_sleep_min")
    if last.get("delta") is not None and last["delta"] <= -60:
        c.add(0.35, f"last night was {abs(last['delta']):.0f} min shorter than usual")
    if wd:
        c.add(0.25, f"{wd['weekday']} is usually a short night for you")
    start = target_bedtime - WIND_DOWN_MIN
    c.block = dict(start=_to_hhmm(start), end=_to_hhmm(target_bedtime), minutes=WIND_DOWN_MIN,
                   title="Wind down: screens off, lights low")
    c.note = f"Aim to be in bed by {_to_hhmm(target_bedtime)} (you usually go to bed around {_to_hhmm(bedtime)})."
    return c


def _recover_between(summary: dict, sig: dict, free: list[dict]) -> Candidate:
    c = Candidate("recover_between")
    cal = summary.get("calendar")
    if not cal:
        return c
    strained = summary["recovery_zone"] in ("yellow", "red") or (sig.get("hrv") or {}).get("status") == "below"
    if cal["busy_hours"] >= 6 and strained:
        c.add(min(0.8, 0.3 + (cal["busy_hours"] - 6) * 0.1),
              f"{cal['busy_hours']:g} busy hours on the calendar while recovery is not fully back")
    if cal.get("meeting_count", 0) >= 5 and strained:
        c.add(0.2, f"{cal['meeting_count']} meetings today")
    c.block = find_slot(free, 15, prefer=(12 * 60, 15 * 60))
    if c.block:
        c.block["title"] = "Short break: step outside, no screens"
    else:
        c.actionability = 0.5
    return c


def _go_hard(summary: dict, sig: dict, free: list[dict], bedtime: int) -> Candidate:
    c = Candidate("go_hard")
    load, hrv, sleep = sig.get("load") or {}, sig.get("hrv") or {}, sig.get("sleep") or {}
    blockers = [
        summary["recovery_zone"] != "green",
        hrv.get("status") == "below",
        load.get("ratio", 1.0) > 1.1,
        load.get("consecutive_hard_days", 0) >= 2,
        sleep.get("shortfall_min", 0) >= 120,
    ]
    if any(blockers):
        return c
    c.add(0.4, f"recovery is {summary['metrics'][0]['value']:g}%, in the green zone")
    if _metric(summary, "recovery_score").get("status") == "better":
        c.add(0.2, "recovery is high for you")
    if load and load["ratio"] < 0.8:
        c.add(0.25, f"training load is light ({load['ratio']:g}x your 4-week average)")
    if hrv.get("status") == "above":
        c.add(0.15, "HRV is above your normal range this week")
    c.block = find_slot(free, 60, latest_end=bedtime - HARD_MIN_BEFORE_BED)
    if c.block:
        c.block["title"] = "Hard session: intervals or heavy strength"
    else:
        c.actionability = 0.3
        c.note = "No free hour early enough today; consider tomorrow."
    return c


# ---------------- entry point ----------------

REPEAT_DAMPING = 0.6      # same focus already chosen on each of the last REPEAT_DAYS days ...
REPEAT_DAYS = 2
REPEAT_OVERRIDE = 0.75    # ... unless the evidence is this strong


def choose_focus(summary: dict, panel: pd.DataFrame, today: date, now: datetime | None = None,
                 recent_focuses: list[str] | None = None) -> dict:
    """The day's focus as a plain dict (stored, rendered and later sent to the LLM).

    `recent_focuses` are the focuses chosen on previous days, most recent first. Repeating the
    same advice day after day is how people learn to ignore it, so a focus that was already
    chosen on each of the last two days needs stronger evidence to be chosen again.
    """
    sig = summary.get("signals") or {}
    free = (summary.get("calendar") or {}).get("free_windows") or []
    bedtime = usual_bedtime(panel, today) or DEFAULT_BEDTIME
    target_bedtime = max(EARLIEST_TARGET_BEDTIME, bedtime - 30)

    if not summary.get("last_night_scored"):
        return dict(focus="none", title="Waiting for last night's data", score=0.0, reasons=[],
                    block=None, note="Your plan will be based on today's recovery once WHOOP has scored it.",
                    considered=[])

    candidates = [
        _lower_intensity(summary, sig, free, bedtime),
        _prioritize_sleep(summary, sig, bedtime, target_bedtime),
        _recover_between(summary, sig, free),
        _go_hard(summary, sig, free, bedtime),
    ]
    recent = (recent_focuses or [])[:REPEAT_DAYS]
    for c in candidates:
        if len(recent) == REPEAT_DAYS and all(r == c.key for r in recent) and c.evidence < REPEAT_OVERRIDE:
            c.actionability *= REPEAT_DAMPING
    considered = sorted(((c.key, c.score) for c in candidates), key=lambda kv: (-kv[1], PRIORITY.index(kv[0])))
    best_key, best_score = considered[0]
    if best_score < THRESHOLD:
        return dict(focus="none", title=TITLES["none"], score=best_score, block=None,
                    reasons=["your recovery, sleep and training load are within your usual range"],
                    note="Keep your normal plan.", considered=considered)
    best = next(c for c in candidates if c.key == best_key)
    reasons = [r for _, r in sorted(best.triggers, key=lambda t: -t[0])]
    return dict(focus=best.key, title=TITLES[best.key], score=best_score, reasons=reasons,
                block=best.block, note=best.note, considered=considered)
