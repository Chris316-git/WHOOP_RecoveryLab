"""Safety validator for the AI's recommendation. Pure logic.

The AI may decide and design freely, but its answer is used only if every check passes:

* shape: known focus type, confidence level and action type, sane lengths;
* evidence: every reason cites ids that exist in the case file;
* numbers: every number in the text appears in the evidence (or is the action's own time/length);
* safety: no hard session when the data argues against one, no medical, medication or diet advice,
  hypotheses are hedged;
* feasibility: a calendar block lies inside a free window (a wind-down: in the evening), starts
  after now, has a sensible length and ends early enough before the usual bedtime.

The calendar itself is only ever written after the user taps "Add to calendar".
"""
import json
import re

from src.planner.focus import CAVEAT, TITLES

FOCUS_TYPES = {"lower_intensity", "prioritize_sleep", "recover_between", "go_hard", "other", "none"}
CONFIDENCE = {"high", "moderate", "tentative"}
ACTION_TYPES = {"calendar_block", "guidance", "none"}
BANNED = ("under-recovered", "underrecovered", "overtrain", "burnout",
          "diagnos", "disease", "illness", "disorder", "medication", "medicine", "supplement", "pill", "drug",
          "calorie", "fasting", "diet", "alcohol", "doctor", "emergency", "dangerous", "guarantee", "you must")
HARD_WORDS = ("interval", "hard session", "hard workout", "heavy", "max effort", "sprint", "race", "tempo", "hiit",
              "intense", "all-out", "threshold")
HEDGES = ("possibly", "may ", "might", "perhaps", "could", "maybe", "likely")
LIMITS = dict(title=70, headline=320, reason=220, action_title=80, note=260)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_EVIDENCE_ID = re.compile(r"\bE\d+\b")
_TIME = re.compile(r"\b(?:[01]?\d|2[0-4]):[0-5]\d\b")
_HHMM = re.compile(r"^([01]?\d|2[0-4]):([0-5]\d)$")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _clock(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUMBER.findall(_EVIDENCE_ID.sub("", text))}


def validate(out: dict, case: dict, summary: dict) -> tuple[dict | None, list[str]]:
    """(focus dict ready for the email, []) or (None, list of problems)."""
    problems: list[str] = []
    if not isinstance(out, dict):
        return None, ["not an object"]
    ft, conf = out.get("focus_type"), out.get("confidence")
    title, headline = str(out.get("title") or "").strip(), str(out.get("headline") or "").strip()
    if ft not in FOCUS_TYPES:
        problems.append("unknown focus_type")
    if ft != "none" and conf not in CONFIDENCE:
        problems.append("unknown confidence")
    if not title or len(title) > LIMITS["title"]:
        problems.append("title length")
    if not headline or len(headline) > LIMITS["headline"]:
        problems.append("headline length")

    ids = {e["id"] for e in case["evidence"]}
    reasons, counter = out.get("reasons") or [], out.get("counter") or []
    if ft != "none" and not 1 <= len(reasons) <= 3:
        problems.append("reasons count")
    if len(counter) > 2:
        problems.append("counter count")
    for r in [*reasons, *counter]:
        if not isinstance(r, dict) or not r.get("text") or len(str(r["text"])) > LIMITS["reason"]:
            problems.append("reason format")
            continue
        cited = r.get("evidence") or []
        if not cited or any(c not in ids for c in cited):
            problems.append("evidence ids")

    action = out.get("action") or {"type": "none"}
    kind = action.get("type")
    if kind not in ACTION_TYPES:
        problems.append("unknown action type")
    uncertainty = str(out.get("uncertainty") or "").strip() or None
    hypothesis = str(out.get("hypothesis") or "").strip() or None
    for note in (uncertainty, hypothesis):
        if note and len(note) > LIMITS["note"]:
            problems.append("note length")
    if hypothesis and not any(h in hypothesis.lower() for h in HEDGES):
        problems.append("unhedged hypothesis")

    # Feasibility of the action, and the numbers it is allowed to introduce.
    allowed = _numbers(json.dumps(case, ensure_ascii=False))
    block = None
    cons = case.get("constraints") or {}
    if kind == "calendar_block":
        start, length = str(action.get("start") or ""), action.get("minutes")
        a_title = str(action.get("title") or "").strip()
        bad_title = not a_title or len(a_title) > LIMITS["action_title"]
        if not _HHMM.match(start) or not isinstance(length, int) or bad_title:
            problems.append("action format")
        else:
            s = _minutes(start)
            if ft == "prioritize_sleep" and s < 12 * 60:   # a wind-down after midnight belongs to tonight
                s += 1440
            e = s + length
            now = _minutes(case["now"]) if case.get("now") else None
            bed = _minutes(cons["usual_bedtime"]) if cons.get("usual_bedtime") else 23 * 60
            bed = bed + 1440 if bed < 12 * 60 else bed
            if now is not None and s < now:
                problems.append("block in the past")
            if ft == "prioritize_sleep":
                if not (10 <= length <= 120 and s >= 18 * 60 and e <= 26 * 60):
                    problems.append("wind-down timing")
            else:
                windows = cons.get("free_windows")
                if windows is None:
                    problems.append("no calendar for a block")
                elif not any(_minutes(w["start"]) <= s and e <= _minutes(w["end"]) for w in windows):
                    problems.append("block not in free time")
                if not 10 <= length <= 300:
                    problems.append("block length")
                if e > bed - (180 if ft == "go_hard" else 60):
                    problems.append("block too close to bedtime")
            allowed |= _numbers(start) | {float(length)} | _numbers(_clock(e))
            # "20 minutes earlier than usual": differences between the block and times in the evidence
            for t in _TIME.findall(json.dumps(case["evidence"])):
                ref = _minutes(t)
                for x in (s, e):
                    for r in (ref, ref + 1440):
                        if 0 < abs(x - r) <= 180:
                            allowed.add(float(abs(x - r)))
            block = dict(start=_clock(s), end="24:00" if e == 1440 else _clock(e), minutes=length, title=a_title)
    elif kind == "guidance":
        a_title = str(action.get("title") or "").strip()
        if not a_title or len(a_title) > LIMITS["action_title"]:
            problems.append("action format")

    texts = [title, headline, *(str(r.get("text", "")) for r in [*reasons, *counter] if isinstance(r, dict)),
             str(action.get("title") or ""), uncertainty or "", hypothesis or ""]
    blob = " ".join(texts)
    if _numbers(blob) - allowed:
        problems.append("numbers")
    lowered = blob.lower()
    if any(w in lowered for w in BANNED):
        problems.append("banned wording")
    if not cons.get("hard_session_allowed", True):
        action_text = str(action.get("title") or "").lower()
        if ft == "go_hard" or any(w in action_text for w in HARD_WORDS):
            problems.append("hard session against the data")
    if cons.get("experiment_tonight") == "control" and any(w in lowered for w in cons.get("experiment_conflict_words")
                                                              or ["screen"]):
        problems.append("conflicts with experiment")
    if ft == "none" and kind == "calendar_block":
        problems.append("block on a no-change day")
    needs_block = ft == "prioritize_sleep" or (ft in ("go_hard", "recover_between") and cons.get("free_windows"))
    if needs_block and kind != "calendar_block":
        problems.append("missing calendar block")

    if problems:
        return None, sorted(set(problems))

    rule = summary.get("focus") or {}
    considered = rule.get("considered") or []
    score = dict((k, s) for k, s in considered).get(ft, 0.0)
    guidance = action.get("title") if kind == "guidance" else None
    small = [x for x in (hypothesis, uncertainty) if x]
    if rule.get("focus") and rule["focus"] != ft:
        small.append(f"The rule engine would have suggested: {TITLES.get(rule['focus'], rule['focus']).lower()}.")
    return dict(
        focus=ft, title=title, score=float(score), confidence=conf if ft != "none" else None, headline=headline,
        reasons=[str(r["text"]) for r in reasons], counter=[str(r["text"]) for r in counter],
        alternatives=small, note=guidance, caveat=CAVEAT if ft != "none" else None, block=block,
        considered=considered, schedulable=block is not None, engine="ai",
        evidence_used=sorted({c for r in [*reasons, *counter] for c in r.get("evidence", [])},
                             key=lambda x: int(x[1:])),
    ), []


def validate_proposal(p, case: dict) -> tuple[dict | None, list[str]]:
    """An optional experiment proposal. A bad proposal is dropped; the day's plan still stands."""
    if not p:
        return None, []
    options = {o["preset"]: o for o in (case.get("constraints") or {}).get("experiment_options") or []}
    why = str(p.get("why") or "").strip() if isinstance(p, dict) else ""
    ids = {e["id"] for e in case["evidence"]}
    problems = []
    if not isinstance(p, dict) or p.get("preset") not in options:
        problems.append("proposal not allowed")
    if not why or len(why) > 240:
        problems.append("proposal length")
    cited = p.get("evidence") or [] if isinstance(p, dict) else []
    if not cited or any(c not in ids for c in cited):
        problems.append("proposal evidence ids")
    if _numbers(why) - _numbers(json.dumps(case, ensure_ascii=False)):
        problems.append("proposal numbers")
    if any(w in why.lower() for w in BANNED):
        problems.append("proposal wording")
    if problems:
        return None, ["proposal dropped: " + ", ".join(problems)]
    return dict(preset=p["preset"], why=why, evidence=cited, **{k: options[p["preset"]][k]
                                                                for k in ("title", "question", "nights")}), []
