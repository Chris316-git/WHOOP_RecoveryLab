"""Reasoning evaluation: how is the AI doing compared with the rule engine? Pure logic.

Works on stored daily plans (both engines' choices, the validator's verdict, the user's
response and the measured outcome). With REASONING_MODE=ai the AI's plan is shown whenever it
passes the checks, so adherence by engine compares AI days with fallback days, which are not
a random sample; treat those numbers as descriptive.
"""
from collections import Counter

TOPICS = ("history", "habits", "calendar")   # evidence that only personal context can provide


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 2) if d else None


def evaluate_plans(plans: list[dict]) -> dict:
    """plans: dicts with engine, focus, rule_focus, ai_status, ai_problems, ai_output, evidence,
    response, outcome. Returns a small report of plain numbers."""
    attempted = [p for p in plans if p.get("ai_status") not in (None, "off")]
    status = Counter(p["ai_status"] for p in attempted)
    problems = Counter(x for p in attempted for x in (p.get("ai_problems") or []))
    ok = [p for p in attempted if p["ai_status"] == "ok"]

    def ai_focus(p: dict) -> str | None:
        return (p.get("ai_output") or {}).get("focus_type")

    agree = sum(1 for p in ok if ai_focus(p) == (p.get("rule_focus") or {}).get("focus"))
    ai_none = sum(1 for p in ok if ai_focus(p) == "none")

    def cites_personal(p: dict) -> bool:
        topic = {e["id"]: e["topic"] for e in (p.get("evidence") or {}).get("evidence", [])}
        out = p.get("ai_output") or {}
        cited = {c for r in [*(out.get("reasons") or []), *(out.get("counter") or [])] for c in r.get("evidence", [])}
        return any(topic.get(c) in TOPICS for c in cited)

    by_engine = {}
    for engine in ("ai", "rules"):
        shown = [p for p in plans if p.get("engine", "rules") == engine and p.get("focus") not in (None, "none")]
        measured = [p for p in shown if p.get("outcome") in ("done", "partly", "not_done")]
        by_engine[engine] = dict(
            days_with_a_focus=len(shown),
            added_to_calendar=_rate(sum(p.get("response") == "added" for p in shown), len(shown)),
            dismissed_or_not_useful=_rate(sum(p.get("response") in ("dismissed", "not_useful") for p in shown),
                                          len(shown)),
            done_or_partly=_rate(sum(p["outcome"] in ("done", "partly") for p in measured), len(measured)),
        )
    return dict(
        days=len(plans),
        ai_attempts=len(attempted),
        evidence_accuracy=dict(passed_checks=_rate(len(ok), len(attempted)), status=dict(status),
                               rejection_reasons=dict(problems.most_common())),
        safety=dict(blocked_hard_sessions=problems.get("hard session against the data", 0),
                    blocked_wording=problems.get("banned wording", 0)),
        agreement_with_rules=_rate(agree, len(ok)),
        ai_no_change_days=_rate(ai_none, len(ok)),
        personalization=dict(ai_plans_citing_history_habits_or_calendar=_rate(sum(map(cites_personal, ok)), len(ok))),
        by_engine=by_engine,
    )
