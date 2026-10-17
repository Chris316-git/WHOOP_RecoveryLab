"""What the morning email says about experiments. Pure logic.

* Active experiment: today's assignment from the randomized schedule, a one-tap question about
  the previous treatment day (a wearable hint may be shown, but only the answer counts), and,
  after the last night, the analysis.
* Finished experiment awaiting a decision: the result with keep / extend / drop.
* Proposal: when nothing is running, which presets the AI may propose (eligibility is decided
  here, in code), and a proposal made today that is waiting for Start / Not now.
"""
from datetime import date, timedelta

import pandas as pd

from src.experiments.analysis import analyze, explain
from src.experiments.design import arm_on
from src.experiments.presets import MAX_EXTENSIONS, PRESETS, preset

GRACE_DAYS = 2
DEFAULT_BEDTIME = 23 * 60
DECISION_DAYS = 3          # show a finished result with its buttons for this many days
PROPOSAL_EVERY_DAYS = 7    # at most one proposal a week
DECLINED_QUIET_DAYS = 30   # a declined preset is not proposed again for a month
REPEAT_QUIET_DAYS = 60     # nor one that finished recently
MIN_HISTORY_DAYS = 21      # enough data for a baseline before experimenting
NIGHT_PRESETS = {"screens_off_30"}


def _clock(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _cell(panel: pd.DataFrame, day: date, col: str):
    if col not in panel or day not in panel.index:
        return None
    v = panel.at[day, col]
    return None if v is None or pd.isna(v) else v


def nights_with_outcomes(exp: dict, adherence: dict[str, str], panel: pd.DataFrame) -> list[dict]:
    spec = preset(exp["preset"])
    cols = (spec["outcome"]["column"], spec["secondary"]["column"])
    out = []
    for s in exp["schedule"]:
        d = date.fromisoformat(s["day"])
        row = dict(s, adherence=adherence.get(s["day"]))
        for c in cols:
            v = _cell(panel, d, c)
            row[c] = None if v is None else float(v)
        out.append(row)
    return out


def recommended_step(verdict: str, extensions: int) -> tuple[str, list[str]]:
    """(recommended next step, allowed steps). Decided in code from the pre-specified verdict."""
    can_extend = extensions < MAX_EXTENSIONS
    if verdict == "helped":
        return "keep", ["keep", "drop"]
    if verdict in ("worse", "no_meaningful_effect"):
        return "drop", ["drop", "keep"]
    if can_extend:
        return "extend", ["extend", "drop", "keep"]
    return "drop", ["drop", "keep"]


def experiment_today(exp: dict, adherence: dict[str, str], panel: pd.DataFrame, today: date,
                     usual_bedtime: int | None) -> dict:
    spec = preset(exp["preset"])
    start = date.fromisoformat(exp["schedule"][0]["day"])
    last = date.fromisoformat(exp["schedule"][-1]["day"])
    info = dict(id=exp["id"], preset=exp["preset"], title=spec["title"], question=spec["question"],
                nights=exp["nights"], start_day=exp["start_day"])
    night_word = "Tonight" if exp["preset"] in NIGHT_PRESETS else "Today"

    tonight = arm_on(exp["schedule"], today)
    if tonight:
        bed = usual_bedtime or DEFAULT_BEDTIME
        info["night"] = (today - start).days + 1
        info["arm"] = tonight["arm"]
        if tonight["arm"] == "treatment":
            info["tonight"] = spec["tonight_treatment"].format(bed=_clock(bed), bed_minus_30=_clock(bed - 30))
        else:
            unit = "night" if exp["preset"] in NIGHT_PRESETS else "day"
            info["tonight"] = f"{night_word} is a comparison {unit}: {spec['control']}"

    yesterday = today - timedelta(days=1)
    prev = arm_on(exp["schedule"], yesterday)
    if prev and prev["arm"] == "treatment" and adherence.get(prev["day"]) is None:
        hint = None
        start_local = _cell(panel, yesterday, "sleep_start_local")
        if start_local is not None and exp["preset"] in NIGHT_PRESETS:
            t = pd.Timestamp(start_local)
            hint = f"For reference, WHOOP recorded your sleep starting around {t.hour:02d}:{t.minute:02d}."
        info["ask"] = dict(day=prev["day"], question=spec["adherence_question"], hint=hint)

    if today > last:
        last_scored = _cell(panel, last, spec["outcome"]["column"]) is not None
        grace_over = today >= last + timedelta(days=GRACE_DAYS + 1)
        if (last_scored and "ask" not in info) or grace_over:   # wait for the last answer too
            result = analyze(nights_with_outcomes(exp, adherence, panel), spec)
            step, steps = recommended_step(result["primary"]["itt"]["verdict"], exp.get("extensions") or 0)
            result.update(recommended=step, steps=steps)
            info.update(done=True, result=result, explanation=explain(result, spec))
        else:
            info["waiting"] = "The results come once the last night's data (and your answer above) are in."
    return info


def decision_card(exp: dict, today: date) -> dict | None:
    """A finished experiment whose result still waits for keep / extend / drop."""
    if exp["status"] != "completed" or exp.get("next_step") or not exp.get("result"):
        return None
    if exp.get("ended_on") and today > date.fromisoformat(exp["ended_on"]) + timedelta(days=DECISION_DAYS):
        return None
    spec = preset(exp["preset"])
    r = exp["result"]
    return dict(id=exp["id"], preset=exp["preset"], title=spec["title"], nights=exp["nights"], done=True,
                start_day=exp["start_day"], result=r,
                explanation=r.get("ai_explanation") or explain(r, spec), decide=True)


def _stale_proposal(e: dict, today: date) -> bool:
    return bool(e["status"] == "proposed" and e.get("proposed_on")
                and today - date.fromisoformat(e["proposed_on"]) > timedelta(days=2))


def eligible_presets(experiments: list[dict], today: date, history_days: int) -> list[str]:
    """Presets the AI may propose today (empty when it should not propose anything)."""
    if history_days < MIN_HISTORY_DAYS:
        return []
    if any(e["status"] in ("active", "proposed") and not _stale_proposal(e, today) for e in experiments):
        return []
    proposals = [date.fromisoformat(e["proposed_on"]) for e in experiments if e.get("proposed_on")]
    if proposals and today - max(proposals) < timedelta(days=PROPOSAL_EVERY_DAYS):
        return []
    blocked = set()
    for e in experiments:
        when = date.fromisoformat(e.get("ended_on") or e.get("proposed_on") or e["start_day"])
        if e["status"] == "declined" and today - when < timedelta(days=DECLINED_QUIET_DAYS):
            blocked.add(e["preset"])
        if e["status"] in ("completed", "stopped") and today - when < timedelta(days=REPEAT_QUIET_DAYS):
            blocked.add(e["preset"])
    return [k for k in PRESETS if k not in blocked]
