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

from src.planner.habits import easy_activity, hard_activity
from src.report.signals import HARD_STRAIN

THRESHOLD = 0.45
PRIORITY = ["lower_intensity", "prioritize_sleep", "recover_between", "go_hard"]

HARD_MIN_BEFORE_BED = 180      # hard sessions end at least 3 h before the target bedtime
EASY_MIN_BEFORE_BED = 60
PREFERRED_START, PREFERRED_END = 16 * 60, 19 * 60   # late afternoon, used to break ties
DEFAULT_BEDTIME = 23 * 60
EARLIEST_TARGET_BEDTIME = 21 * 60 + 30
WIND_DOWN_MIN = 45
BEDTIME_HISTORY_DAYS = 14

# Focuses whose suggested block can go on the calendar (always optional, one tap). A focus
# with no block ("nothing needs to change") never gets calendar buttons.
SCHEDULABLE = {"lower_intensity", "prioritize_sleep", "recover_between", "go_hard"}

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

    Picks the start closest to the `prefer` range (your usual workout time, or late afternoon
    by default); among equally close options, the earliest.
    """
    lo, hi = prefer if prefer else (0, 0)
    best = None
    for w in free_windows:
        s, e = _to_min(w["start"]), _to_min(w["end"])
        if latest_end is not None:
            e = min(e, latest_end)
        if e - s < minutes:
            continue
        start = min(max(s, lo), e - minutes) if prefer else s   # as close to the preferred range as fits
        quarter = -(-start // 15) * 15                          # round up to :00, :15, :30 or :45 ...
        if quarter <= e - minutes:
            start = quarter
        elif (start // 15) * 15 >= s:                            # ... or down, if up no longer fits
            start = (start // 15) * 15
        distance = 0 if lo <= start <= hi else min(abs(start - lo), abs(start - hi))
        if prefer is None:
            distance = start
        if best is None or (distance, start) < best:
            best = (distance, start)
    if best is None:
        return None
    start = best[1]
    return dict(start=_to_hhmm(start), end=_to_hhmm(start + minutes), minutes=minutes)


# ---------------- candidates ----------------

def _metric(summary: dict, key: str) -> dict:
    return next((m for m in summary["metrics"] if m["key"] == key), {})


def _lower_intensity(summary: dict, sig: dict, free: list[dict], bedtime: int, habits: dict | None = None) -> Candidate:
    c = Candidate("lower_intensity")
    load, hrv, rhr, sleep = sig.get("load"), sig.get("hrv"), sig.get("resting_hr"), sig.get("sleep")
    if summary["recovery_zone"] == "red":
        c.add(0.6, f"recovery is {summary['metrics'][0]['value']:g}%, in the red zone")
    if load:
        if load["ratio"] > 1.3:
            c.add(min(1.0, (load["ratio"] - 1.3) / 0.3 * 0.5 + 0.3),
                  f"training load is {load['ratio']:g}x your 4-week average")
        if load["consecutive_hard_days"] >= 2:
            c.add(0.2 * load["consecutive_hard_days"], f"{load['consecutive_hard_days']} hard days in a row")
        elif load.get("yesterday_load") is not None and load["yesterday_load"] >= HARD_STRAIN:
            c.add(0.2, f"yesterday was a hard day (strain {load['yesterday_load']:g})")
    if hrv and hrv["status"] == "below":
        c.add(0.4, f"HRV has been below your normal range this week ({hrv['recent_mean']:g} ms "
                   f"vs {hrv['normal_low']:g}-{hrv['normal_high']:g})")
    if rhr and rhr["status"] == "above":
        c.add(0.3, f"resting heart rate is above your normal range this week ({rhr['recent_mean']:g} bpm)")
    if _metric(summary, "hrv_rmssd_milli").get("status") == "worse":
        c.add(0.2, "last night's HRV was low for you")
    if sleep and sleep["shortfall_min"] / max(1, sleep["nights_measured"]) >= 60:
        c.add(0.2, f"you are behind on sleep this week ({_hm(sleep['shortfall_min'])} over "
                   f"{sleep['nights_measured']} nights)")
    act = easy_activity(habits)
    c.block = find_slot(free, act["minutes"], latest_end=bedtime - EASY_MIN_BEFORE_BED,
                        prefer=act["prefer"] or (PREFERRED_START, PREFERRED_END))
    if c.block:
        c.block["title"] = act["title"]
        c.note = act["basis"]
    return c


def _hm(minutes: float) -> str:
    minutes = int(round(minutes))
    return f"{minutes // 60}h {minutes % 60:02d}m"


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
        if short7 >= 7 * 60:  # an hour or more short per night: a problem even if it is your usual
            c.add(weight * min(0.6, 0.3 + (short7 - 420) / 420 * 0.3),
                  f"you have averaged {_hm(short7 / 7)} below your need per night")
    last = _metric(summary, "total_sleep_min")
    if last.get("delta") is not None and last["delta"] <= -60:
        c.add(0.35, f"last night was {abs(last['delta']):.0f} min shorter than usual")
    elif last.get("delta") is not None and last["delta"] <= -30:
        c.add(0.2, f"last night was {abs(last['delta']):.0f} min shorter than usual")
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


def hard_day_blockers(summary: dict, sig: dict) -> list[str]:
    """Why a hard session is NOT advised today (empty list = nothing stands in the way)."""
    load, hrv, sleep = sig.get("load") or {}, sig.get("hrv") or {}, sig.get("sleep") or {}
    out = []  # most informative first; the recovery zone is already shown at the top of the email
    if hrv.get("status") == "below":
        out.append("HRV is below your normal range")
    if load.get("consecutive_hard_days", 0) >= 2:
        out.append(f"{load['consecutive_hard_days']} hard days in a row")
    if load.get("ratio", 1.0) > 1.1:
        out.append(f"recent load is already {load['ratio']:g}x your 4-week average")
    if sleep.get("shortfall_min", 0) >= 120:
        out.append("you are behind on sleep")
    if summary["recovery_zone"] != "green":
        out.append(f"recovery is {summary['recovery_zone']}, not green")
    return out


def _go_hard(summary: dict, sig: dict, free: list[dict], bedtime: int, habits: dict | None = None) -> Candidate:
    c = Candidate("go_hard")
    load, hrv = sig.get("load") or {}, sig.get("hrv") or {}
    if hard_day_blockers(summary, sig):
        return c
    c.add(0.4, f"recovery is {summary['metrics'][0]['value']:g}%, in the green zone")
    if _metric(summary, "recovery_score").get("status") == "better":
        c.add(0.2, "recovery is high for you")
    if load and load["ratio"] < 0.8:
        c.add(0.25, f"training load is light ({load['ratio']:g}x your 4-week average)")
    if hrv.get("status") == "above":
        c.add(0.15, "HRV is above your normal range this week")
    act = hard_activity(habits)
    c.block = find_slot(free, act["minutes"], latest_end=bedtime - HARD_MIN_BEFORE_BED,
                        prefer=act["prefer"] or (PREFERRED_START, PREFERRED_END))
    if c.block:
        c.block["title"] = act["title"]
        c.note = act["basis"]
    else:
        c.actionability = 0.3
        c.note = f"No free {act['minutes']} minutes early enough today; consider tomorrow."
    return c


# ---------------- entry point ----------------

# ---------------- confidence, counter-evidence, alternatives ----------------

CONFIDENCE_BANDS = [(0.75, "high"), (0.6, "moderate"), (0.0, "tentative")]
HEADLINES = {  # wording follows how strong the evidence is
    "lower_intensity": {"high": "Keep today light.", "moderate": "A lighter day is probably the better call.",
                        "tentative": "Consider keeping today on the lighter side."},
    "prioritize_sleep": {"high": "Make tonight's sleep the priority.",
                         "moderate": "An earlier night would probably help.",
                         "tentative": "If you can, aim for an earlier night."},
    "recover_between": {"high": "Protect a few short breaks today.",
                        "moderate": "A short break or two would probably help today.",
                        "tentative": "If the day allows, take a short break."},
    "go_hard": {"high": "Today is a good day to push.", "moderate": "Today looks like a good day for a harder session.",
                "tentative": "A harder session looks reasonable today."},
}
CAVEAT = "These are rules of thumb from your data, not a diagnosis. Adjust to how you actually feel."


def confidence(score: float) -> str:
    return next(label for cut, label in CONFIDENCE_BANDS if score >= cut)


def counter_evidence(focus: str, summary: dict, sig: dict) -> list[str]:
    """Signals that point the other way, so the advice never looks more certain than it is."""
    out = []
    zone = summary["recovery_zone"]
    rhr, hrv, sleep, load = sig.get("resting_hr"), sig.get("hrv"), sig.get("sleep"), sig.get("load")
    perf = _metric(summary, "sleep_performance_pct")
    if focus == "lower_intensity":
        if zone == "green":
            out.append(f"recovery is {summary['metrics'][0]['value']:g}%, in the green zone")
        if rhr and rhr["status"] in ("within", "below"):
            out.append(f"resting heart rate is {rhr['status']} your normal range")
        if perf.get("value") is not None and perf.get("status") in ("typical", "better"):
            out.append(f"sleep performance was {perf['value']:g}%, normal for you")
        if sleep and sleep["shortfall_min"] < 60:
            out.append("you are not behind on sleep")
    elif focus == "prioritize_sleep":
        if zone == "green":
            out.append("your recovery is holding up so far")
        if hrv and hrv["status"] in ("within", "above"):
            out.append(f"HRV is {hrv['status']} your normal range")
    elif focus == "recover_between":
        if zone == "green":
            out.append("your recovery is good")
    elif focus == "go_hard":
        if sleep and 60 <= sleep["shortfall_min"] < 120:
            out.append("you are slightly behind on sleep this week")
        if rhr and rhr["status"] == "above":
            out.append("resting heart rate is above your normal range")
        if load and load["level"] == "high":
            out.append("training load is on the high side")
    return out


def alternatives(focus: str, considered: list, summary: dict, sig: dict) -> list[str]:
    """Why this focus and not another one."""
    out = []
    if focus != "go_hard":
        blockers = hard_day_blockers(summary, sig)
        if blockers:
            out.append("Not a hard session today: " + "; ".join(blockers[:2]) + ".")
    runner = next(((k, sc) for k, sc in considered if k != focus and sc > 0), None)
    if runner and runner[0] != "go_hard":
        out.append(f"Also considered: {TITLES[runner[0]].lower()} (weaker evidence today).")
    return out


REPEAT_DAMPING = 0.6      # same focus already chosen on each of the last REPEAT_DAYS days ...
REPEAT_DAYS = 2
REPEAT_OVERRIDE = 0.75    # ... unless the evidence is this strong
NOT_USEFUL_DAMPING = 0.6  # the user said this kind of suggestion was not useful (recently)


def choose_focus(summary: dict, panel: pd.DataFrame, today: date, now: datetime | None = None,
                 recent_focuses: list[str] | None = None, not_useful: set[str] | None = None,
                 habits: dict | None = None) -> dict:
    """The day's focus as a plain dict (stored, rendered and later sent to the LLM).

    `recent_focuses` are the focuses chosen on previous days, most recent first. Repeating the
    same advice day after day is how people learn to ignore it, so a focus that was already
    chosen on each of the last two days needs stronger evidence to be chosen again.

    `not_useful` are focuses the user explicitly marked "not useful" recently; they also need
    stronger evidence. Not responding is never treated as a rejection.

    `habits` (src/planner/habits.py) turns the generic easy and hard blocks into versions of
    the activities the user actually does, at their usual time.
    """
    sig = summary.get("signals") or {}
    free = (summary.get("calendar") or {}).get("free_windows") or []
    bedtime = usual_bedtime(panel, today) or DEFAULT_BEDTIME
    target_bedtime = max(EARLIEST_TARGET_BEDTIME, bedtime - 30)

    if not summary.get("last_night_scored"):
        return dict(focus="none", title="Waiting for last night's data", score=0.0, confidence=None,
                    headline="Your plan will be based on today's recovery once WHOOP has scored it.",
                    reasons=[], counter=[], alternatives=[], caveat=None, block=None, note=None, considered=[],
                    schedulable=False)

    candidates = [
        _lower_intensity(summary, sig, free, bedtime, habits),
        _prioritize_sleep(summary, sig, bedtime, target_bedtime),
        _recover_between(summary, sig, free),
        _go_hard(summary, sig, free, bedtime, habits),
    ]
    recent = (recent_focuses or [])[:REPEAT_DAYS]
    for c in candidates:
        if len(recent) == REPEAT_DAYS and all(r == c.key for r in recent) and c.evidence < REPEAT_OVERRIDE:
            c.actionability *= REPEAT_DAMPING
        if c.key in (not_useful or set()) and c.evidence < REPEAT_OVERRIDE:
            c.actionability *= NOT_USEFUL_DAMPING
    considered = sorted(((c.key, c.score) for c in candidates), key=lambda kv: (-kv[1], PRIORITY.index(kv[0])))
    best_key, best_score = considered[0]
    if best_score < THRESHOLD:
        hints = ([f"Closest call: {TITLES[best_key].lower()}, but the evidence is weak."]
                 if best_score > 0.25 else [])
        return dict(focus="none", title=TITLES["none"], score=best_score, block=None, confidence=None,
                    headline="Keep your normal plan.",
                    reasons=["your recovery, sleep and training load are within your usual range"],
                    counter=[], alternatives=hints, caveat=None, note=None, considered=considered,
                    schedulable=False)
    best = next(c for c in candidates if c.key == best_key)
    reasons = [r for _, r in sorted(best.triggers, key=lambda t: -t[0])]
    level = confidence(best_score)
    return dict(focus=best.key, title=TITLES[best.key], score=best_score, confidence=level,
                headline=HEADLINES[best.key][level], reasons=reasons,
                counter=counter_evidence(best.key, summary, sig),
                alternatives=alternatives(best.key, considered, summary, sig),
                caveat=CAVEAT, block=best.block, note=best.note, considered=considered,
                schedulable=best.key in SCHEDULABLE and best.block is not None)
