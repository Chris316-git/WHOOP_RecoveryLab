"""What the morning email says about an active experiment. Pure logic.

* Tonight's assignment, from the randomized schedule (treatment or control night).
* A one-tap question about the previous treatment night, if not answered yet. A hint from the
  wearable (when sleep started) may be shown, but only the user's answer counts as adherence.
* After the last night: the analysis (src/experiments/analysis.py), once that night's outcome is
  in, or at the latest GRACE_DAYS later.
"""
from datetime import date, timedelta

import pandas as pd

from src.experiments.analysis import analyze, explain
from src.experiments.design import arm_on
from src.experiments.presets import preset

GRACE_DAYS = 2
DEFAULT_BEDTIME = 23 * 60


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


def experiment_today(exp: dict, adherence: dict[str, str], panel: pd.DataFrame, today: date,
                     usual_bedtime: int | None) -> dict:
    spec = preset(exp["preset"])
    start = date.fromisoformat(exp["schedule"][0]["day"])
    last = date.fromisoformat(exp["schedule"][-1]["day"])
    info = dict(id=exp["id"], title=spec["title"], question=spec["question"], nights=exp["nights"])

    tonight = arm_on(exp["schedule"], today)
    if tonight:
        bed = usual_bedtime or DEFAULT_BEDTIME
        info["night"] = (today - start).days + 1
        info["arm"] = tonight["arm"]
        if tonight["arm"] == "treatment":
            info["tonight"] = (f"Tonight is a {spec['short']} night: screens off from {_clock(bed - 30)}, "
                               f"30 minutes before your usual bedtime ({_clock(bed)}).")
        else:
            info["tonight"] = f"Tonight is a comparison night: {spec['control']}"

    yesterday = today - timedelta(days=1)
    prev = arm_on(exp["schedule"], yesterday)
    if prev and prev["arm"] == "treatment" and adherence.get(prev["day"]) is None:
        start_local = _cell(panel, yesterday, "sleep_start_local")
        hint = None
        if start_local is not None:
            t = pd.Timestamp(start_local)
            hint = f"For reference, WHOOP recorded your sleep starting around {t.hour:02d}:{t.minute:02d}."
        info["ask"] = dict(day=prev["day"], question=spec["adherence_question"], hint=hint)

    if today > last:
        last_scored = _cell(panel, last, spec["outcome"]["column"]) is not None
        grace_over = today >= last + timedelta(days=GRACE_DAYS + 1)
        if (last_scored and "ask" not in info) or grace_over:   # wait for the last answer too
            result = analyze(nights_with_outcomes(exp, adherence, panel), spec)
            info.update(done=True, result=result, explanation=explain(result, spec))
        else:
            info["waiting"] = "The results come once the last night's data (and your answer above) are in."
    return info
