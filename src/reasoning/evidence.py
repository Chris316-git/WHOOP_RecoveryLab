"""Evidence builder: everything the AI may reason about, as numbered, already computed facts.

Each item has an id (E1, E2, ...), a topic and one plain sentence. All numbers in it were
computed in Python; the AI may only cite these items and reuse their numbers. Items cover
today's state, trends against the user's own baseline, training load, sleep, the calendar,
activity habits, and the last 7 days of suggestions with the user's responses and what
actually happened, so the AI can notice patterns such as advice that keeps not being followed.

No raw records, event titles, names or email addresses are included. Pure logic.
"""
from datetime import date, datetime

import pandas as pd

from src.experiments.presets import preset
from src.planner.focus import DEFAULT_BEDTIME, EARLIEST_TARGET_BEDTIME, TITLES, hard_day_blockers, usual_bedtime

HISTORY_DAYS = 7


def _hm(minutes: float) -> str:
    minutes = int(round(minutes))
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _clock(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _metric_text(m: dict) -> str | None:
    if m.get("value") is None:
        return None
    value = _hm(m["value"]) if m["unit"] == "min" else f"{m['value']:g} {m['unit']}".replace(" %", "%")
    if m.get("baseline_median") is None:
        return f"{m['label']} last night: {value} (not enough history for a baseline yet)."
    usual = _hm(m["baseline_median"]) if m["unit"] == "min" else f"{m['baseline_median']:g}"
    return f"{m['label']} last night: {value}, your 30-day median is {usual} ({m['status']} for you)."


def _plan_text(p: dict) -> str:
    title = p.get("title") or TITLES.get(p["focus"], p["focus"])
    block = p.get("final_block") or p.get("block")
    parts = [f"{p['day']}: suggested \"{title}\""]
    if block:
        parts.append(f"block {block['start']}-{block['end']} ({block['title']})")
    response = {None: "no response", "added": "added it to the calendar", "dismissed": "dismissed it",
                "not_useful": "marked it not useful"}.get(p.get("response"), p.get("response"))
    parts.append(f"your response: {response}")
    d = p.get("outcome_detail") or {}
    outcome = p.get("outcome")
    if outcome in ("done", "partly", "not_done"):
        detail = ""
        if "bedtime" in d:
            detail = f", in bed at {d['bedtime']} vs target {d['target']}"
        elif "strain" in d:
            detail = f", strain {d['strain']:g}"
        parts.append(f"outcome from data: {outcome.replace('_', ' ')}{detail}")
    elif outcome:
        parts.append(f"outcome: {outcome.replace('_', ' ')}")
    return "; ".join(parts) + "."


def build_case(summary: dict, panel: pd.DataFrame, today: date, now: datetime | None = None,
               habits: dict | None = None, recent_plans: list[dict] | None = None) -> dict:
    """The case file sent to the AI: numbered evidence plus a few constraints for the action."""
    items: list[tuple[str, str]] = []

    def add(topic: str, text: str | None) -> None:
        if text:
            items.append((topic, text))

    sig = summary.get("signals") or {}
    rec = summary["metrics"][0]
    if rec.get("value") is not None:
        delta = f", {rec['delta']:+g} points vs your usual" if rec.get("delta") is not None else ""
        add("today", f"Recovery today: {rec['value']:g}% ({summary.get('recovery_zone')} zone){delta}.")
    else:
        add("data", "Last night's sleep is not scored yet, so today's recovery is unknown.")
    for m in summary["metrics"][1:]:
        add("last_night", _metric_text(m))
    if summary.get("yesterday_load") is not None:
        add("load", f"Yesterday's strain: {summary['yesterday_load']:g} (14 or more counts as a hard day).")

    hrv, rhr, sleep, load, wd = (sig.get(k) for k in ("hrv", "resting_hr", "sleep", "load", "weekday"))
    if hrv:
        add("trend", f"HRV over the last 7 days: {hrv['recent_mean']:g} ms, {hrv['status']} your normal range "
                     f"of {hrv['normal_low']:g}-{hrv['normal_high']:g} ms (from the 30 days before).")
    if rhr:
        add("trend", f"Resting heart rate over the last 7 days: {rhr['recent_mean']:g} bpm, {rhr['status']} your "
                     f"normal range of {rhr['normal_low']:g}-{rhr['normal_high']:g} bpm.")
    if sleep:
        typical = (f"; in a typical week of the previous month you were {_hm(sleep['typical_shortfall_min'])} short"
                   if sleep.get("typical_shortfall_min") is not None else "")
        source = "WHOOP's estimate" if sleep["need_source"] == "whoop" else "an assumed 8 hours"
        per_night = sleep["shortfall_min"] / max(1, sleep["nights_measured"])
        add("sleep", f"Sleep over the last {sleep['nights_measured']} nights: {_hm(sleep['shortfall_min'])} short of "
                     f"your need of {_hm(sleep['need_min'])} per night ({source}), about {_hm(per_night)} short per "
                     f"night on average, {_n(sleep['nights_short'], 'short night')}, "
                     f"average {_hm(sleep['avg_sleep_min'])} of sleep per night{typical}.")
    if load:
        add("load", f"Training load: the last 7 days average {load['acute_mean']:g} strain, {load['ratio']:g}x your "
                    f"4-week average of {load['chronic_mean']:g}; {_n(load['consecutive_hard_days'], 'hard day')} in a "
                    f"row up to yesterday.")
    if wd:
        add("sleep", f"{wd['weekday']} is usually a short night for you: {abs(wd['gap_min'])} min less on "
                     f"{wd['nights']} recent {wd['weekday']}s.")
    bedtime = usual_bedtime(panel, today)
    if bedtime is not None:
        add("sleep", f"Your usual bedtime over the last 14 nights: {_clock(bedtime)}.")
    blockers = hard_day_blockers(summary, sig) if summary.get("last_night_scored") else []
    if blockers:
        add("safety", "Signals against a hard session today: " + "; ".join(blockers) + ".")

    cal = summary.get("calendar")
    if cal:
        free = ", ".join(f"{w['start']}-{w['end']}" for w in cal["free_windows"]) or "none"
        add("calendar", f"Today's calendar: {_n(cal['event_count'], 'event')}, {cal['busy_hours']:g} busy hours, "
                        f"{_n(cal.get('meeting_count', 0), 'meeting')}. Free from now on: {free}.")
    else:
        add("calendar", "No calendar connected, so free time is unknown.")

    for s in (habits or {}).get("sports", [])[:4]:
        when = (f", usually starting around {_clock(s['usual_start'])}"
                if s.get("usual_start") is not None and "walk" not in s["sport"] else "")
        length = f", typically {s['minutes']} min" if s.get("minutes") else ""
        listed = " (listed by you as an activity you do)" if s.get("chosen") else ""
        add("habits", f"Activity: {s['sport']}, {s['sessions']} sessions in the last {habits['weeks']} weeks"
                      f"{length}{when}{listed}.")
    if not habits:
        add("habits", "Not enough recorded workouts to know your usual activities.")

    for p in sorted(recent_plans or [], key=lambda p: p["day"], reverse=True)[:HISTORY_DAYS]:
        if p.get("focus") and p["focus"] != "none":
            add("history", _plan_text(p))
    if recent_plans and all(p.get("focus") in (None, "none") for p in recent_plans):
        add("history", "No suggestions were made in the last 7 days (nothing needed to change).")

    for k in summary.get("kept_habits") or []:
        add("experiments", f"Earlier experiment \"{k['title']}\": result {k['verdict'].replace('_', ' ')}; "
                           f"you chose to keep the habit.")
    x = summary.get("experiment") or {}
    if x.get("arm"):
        add("experiment", f"An experiment is running: \"{x['title']}\", night {x['night']} of {x['nights']}. "
                          + x["tonight"] + " Do not suggest anything that changes tonight's assignment.")

    evidence = [dict(id=f"E{i}", topic=topic, text=text) for i, (topic, text) in enumerate(items, 1)]
    return dict(
        date=today.isoformat(),
        weekday=today.strftime("%A"),
        now=now.strftime("%H:%M") if now else None,
        evidence=evidence,
        constraints=dict(
            usual_bedtime=_clock(bedtime) if bedtime is not None else None,
            # the rule engine's default target: 30 min before your usual bedtime, not before 21:30
            default_target_bedtime=_clock(max(EARLIEST_TARGET_BEDTIME, (bedtime or DEFAULT_BEDTIME) - 30)),
            free_windows=(cal or {}).get("free_windows") if cal else None,
            hard_session_allowed=not blockers,
            experiment_tonight=x.get("arm"),   # "treatment" | "control" | None
            experiment_conflict_words=list(preset(x["preset"])["conflict_words"]) if x.get("arm") == "control" else [],
            # experiments the AI may propose today (empty: do not propose one)
            experiment_options=summary.get("experiment_options") or [],
        ),
    )
