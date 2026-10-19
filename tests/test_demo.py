import json
from datetime import timedelta

from src.demo.page import build_page, privacy_problems, stress_test
from src.demo.snapshot import example_card, experiment_progress
from src.experiments.design import make_schedule
from src.experiments.simulation import calibration
from src.report.render import render_email
from tests.test_reasoning import TODAY, TZ, ai, panel, run, setup


def snapshot():
    s, case = setup()
    result = run(ai())
    assert result["status"] == "ok"
    s["reasoning"] = {k: result[k] for k in ("status", "problems", "output")}
    rule = s["focus"]
    s["focus"] = result["focus"]
    s["actions"] = {"add": "#", "change": "#", "dismiss": "#"}
    _, email_html, _ = render_email(s)
    sched = make_schedule(TODAY - timedelta(days=3), 14, seed=5)
    exp = dict(id=1, preset="screens_off_30", nights=14, schedule=sched, start_day=sched[0]["day"], status="active")
    return dict(date=TODAY.isoformat(), weekday="Sunday", time="09:15", timezone=TZ, email_html=email_html,
                case=case, reasoning=s["reasoning"], rule_focus=rule, model="test-model",
                stress=stress_test(result["output"], case, dict(s, focus=rule)),
                experiment=experiment_progress([exp], {sched[0]["day"]: "yes"}, panel(), TODAY),
                agent=dict(notes=["Check bedtime tomorrow."], revised=True,
                           trace=[dict(tool="get_metric_history", input=dict(metric="bedtime", days=7),
                                       evidence_id="E20")]),
                coach=dict(question="Fit a workout in this week", reply="Tomorrow at 17:30 is free.",
                           tools_used=["get_today", "get_free_time", "propose_block"], checked=True,
                           proposals=[dict(day="2026-10-19", start="17:30", end="18:00", title="Easy run",
                                           why="Free time.")]),
                calibration=calibration(sims=200), power=[{"nights": 14, 3.0: 0.2, 5.0: 0.4}],
                example_card=example_card())


def test_validator_catches_every_tampered_reply():
    s, case = setup()
    rows = stress_test(ai(), case, s)
    assert len(rows) == 5 and all(r["caught"] for r in rows)


def test_experiment_progress_hides_future_nights():
    sched = make_schedule(TODAY - timedelta(days=3), 14, seed=5)
    exp = dict(id=1, preset="screens_off_30", nights=14, schedule=sched, start_day=sched[0]["day"], status="active")
    x = experiment_progress([exp], {}, panel(), TODAY)
    assert x["night"] == 4 and len(x["nights"]) == 4 and x["total"] == 14
    assert experiment_progress([dict(exp, status="completed")], {}, panel(), TODAY) is None


def test_page_has_every_section_and_no_private_values():
    snap = snapshot()
    html = build_page(snap)
    for text in ("The morning brief", "The daily agent", "Validator stress test", "Running experiment",
                 "False \"clear result\" rate", "What a finished result looks like", "E1",
                 "observe, reason, act, learn", "after one revision", "Check bedtime tomorrow.", "The coach",
                 "Easy run", "get_metric_history"):
        assert text in html
    assert privacy_problems(html, ["secret-key-123"]) == []
    assert privacy_problems(html + "me@example.com /a/token", ["Sunday"]) == [
        "an email address", "an action link", "a private value (Sun...)"]
    json.dumps(snap["case"])   # the case file is plain data
