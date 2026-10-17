from src.reasoning.evaluate import evaluate_plans

EVIDENCE = {"evidence": [dict(id="E1", topic="today"), dict(id="E2", topic="history")]}


def plan(engine, ai_status, ai_focus=None, rule="lower_intensity", response=None, outcome=None, cite="E1",
         problems=None):
    out = dict(focus_type=ai_focus, reasons=[dict(text="x", evidence=[cite])]) if ai_focus else None
    return dict(engine=engine, focus=ai_focus if engine == "ai" else rule, rule_focus=dict(focus=rule),
                ai_status=ai_status, ai_problems=problems, ai_output=out, evidence=EVIDENCE,
                response=response, outcome=outcome)


def test_report():
    plans = [
        plan("ai", "ok", "lower_intensity", response="added", outcome="done"),
        plan("ai", "ok", "prioritize_sleep", cite="E2", outcome="not_done"),
        plan("rules", "rejected", "go_hard", problems=["hard session against the data"], response="dismissed"),
        plan("rules", "off"),
    ]
    r = evaluate_plans(plans)
    assert r["ai_attempts"] == 3 and r["evidence_accuracy"]["passed_checks"] == 0.67
    assert r["safety"]["blocked_hard_sessions"] == 1
    assert r["agreement_with_rules"] == 0.5
    assert r["personalization"]["ai_plans_citing_history_habits_or_calendar"] == 0.5
    assert r["by_engine"]["ai"]["done_or_partly"] == 0.5 and r["by_engine"]["rules"]["dismissed_or_not_useful"] == 0.5
