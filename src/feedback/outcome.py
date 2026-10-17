"""Check yesterday's focus against what the wearable recorded. Pure logic, no I/O.

Most focuses can be verified without asking the user anything:

* "Take it easy"       -> yesterday's strain stayed low
* "Hard session"       -> yesterday's strain reached the hard-day band
* "Protect your sleep" -> last night's sleep started by the target bedtime

"Build breaks" cannot be seen in the data, so it is reported only when the user put the
break on their calendar, and its outcome stays "unmeasured".

Outcomes: done | partly | not_done | no_data | unmeasured. They describe what happened, not
whether it helped: one day cannot show cause and effect, so the recovery numbers that come
with the line are shown side by side without a claim that one caused the other.
"""
from datetime import date, timedelta

import pandas as pd

from src.report.signals import HARD_STRAIN

EASY_STRAIN = 10.0          # WHOOP's "light" band ends around 10
BEDTIME_ON_TIME_MIN = 15    # in bed within 15 min of the target counts as done
BEDTIME_CLOSE_MIN = 45      # within 45 min counts as partly


def _cell(panel: pd.DataFrame, day: date, col: str):
    if col not in panel or day not in panel.index:
        return None
    v = panel.at[day, col]
    return None if v is None or pd.isna(v) else v


def _night_minutes(hhmm_or_ts) -> int:
    """Minutes after midnight, with early-morning times pushed past 24:00 so 23:30 < 00:30."""
    if isinstance(hhmm_or_ts, str):
        h, m = map(int, hhmm_or_ts.split(":"))
    else:
        t = pd.Timestamp(hhmm_or_ts)
        h, m = t.hour, t.minute
    minutes = h * 60 + m
    return minutes + 1440 if minutes < 12 * 60 else minutes


def _hhmm(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _strain_outcome(load: float, want_hard: bool) -> tuple[str, str]:
    s = f"strain {load:g}"
    if want_hard:
        if load >= HARD_STRAIN:
            return "done", f"you got a hard session in ({s})"
        if load >= EASY_STRAIN:
            return "partly", f"it was a moderate day ({s})"
        return "not_done", f"it stayed a light day ({s})"
    if load < EASY_STRAIN:
        return "done", f"you kept it light ({s})"
    if load < HARD_STRAIN:
        return "partly", f"it was a moderate day ({s})"
    return "not_done", f"it ended up a hard day ({s})"


def evaluate(plan: dict, panel: pd.DataFrame, plan_day: date) -> dict | None:
    """Outcome of the focus planned for `plan_day`, using the panel row of that day
    (its strain, and the sleep that started that night). None when there is nothing to report."""
    focus = plan.get("focus")
    if focus in (None, "none"):
        return None
    detail: dict = {}
    if focus in ("lower_intensity", "go_hard"):
        load = _cell(panel, plan_day, "load")
        if load is None:
            outcome, text = "no_data", "no strain data for that day yet"
        else:
            outcome, text = _strain_outcome(float(load), want_hard=focus == "go_hard")
            detail["strain"] = round(float(load), 1)
    elif focus == "prioritize_sleep":
        block = plan.get("final_block") or plan.get("block") or {}
        start = _cell(panel, plan_day, "sleep_start_local")
        if not block.get("end"):
            return None
        target = _night_minutes(block["end"])
        if start is None:
            outcome, text = "no_data", "no sleep recorded for that night yet"
        else:
            actual = _night_minutes(start)
            late = actual - target
            detail.update(bedtime=_hhmm(actual), target=_hhmm(target), minutes_late=late)
            if late <= BEDTIME_ON_TIME_MIN:
                outcome, text = "done", f"in bed by {_hhmm(actual)}, target was {_hhmm(target)}"
            elif late <= BEDTIME_CLOSE_MIN:
                outcome, text = "partly", f"in bed at {_hhmm(actual)}, a little after the {_hhmm(target)} target"
            else:
                outcome, text = "not_done", f"in bed at {_hhmm(actual)}, well after the {_hhmm(target)} target"
    else:  # recover_between and anything future: not visible in the data
        if plan.get("calendar_status") != "scheduled":
            return None
        outcome, text = "unmeasured", "you put it on your calendar"
    before = _cell(panel, plan_day - timedelta(days=1), "recovery_score")
    after = _cell(panel, plan_day, "recovery_score")
    return dict(day=plan_day.isoformat(), focus=focus, title=plan.get("title") or focus, outcome=outcome,
                text=text, detail=detail,
                recovery_before=None if before is None else round(float(before)),
                recovery_after=None if after is None else round(float(after)))
