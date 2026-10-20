import json

from src.agent.daily import check_notes, prepare_case, repeat_problem, run
from src.coach.agent import Toolbox
from tests.test_coach import FakeData
from tests.test_reasoning import ai, setup


def replies(*rs):
    rs = [r if "content" in r else dict(content=[dict(type="text", text=json.dumps(r))]) for r in rs]
    seen = []

    def call(messages):
        seen.append(json.loads(json.dumps(messages, default=str)))
        return rs.pop(0)
    call.seen = seen
    return call


def test_memory_and_notes_become_evidence():
    _, case = setup()
    n = len(case["evidence"])
    out = prepare_case(case, [dict(id=1, kind="constraint", text="No training before work")], ["Check bedtime."])
    assert out["evidence"][n]["topic"] == "memory" and out["evidence"][n + 1]["id"] == f"E{n + 2}"
    assert len(case["evidence"]) == n                                    # the original is not changed


def test_tool_results_are_cited_and_checked():
    s, case = setup()
    eid = f"E{len(case['evidence']) + 1}"                                   # the tool result gets the next id
    call = replies(dict(content=[dict(type="tool_use", id="t1", name="get_metric_history",
                                      input=dict(metric="bedtime", days=7))]),
                   ai(reasons=[dict(text="Your bedtime has averaged 23:30 this week.", evidence=[eid])]))
    r = run(case, s, Toolbox(FakeData(), allowed={"get_metric_history"}), [], "2026-10-17", "k", call=call)
    assert r["status"] == "ok" and r["trace"][0]["evidence_id"] == eid
    assert r["case"]["evidence"][-1]["topic"] == "tool:get_metric_history"
    assert json.loads(call.seen[1][-1]["content"][0]["content"])["evidence_id"] == eid


def test_one_revision_then_rules():
    s, case = setup()
    bad = ai(headline="Sleep 937 extra minutes tonight.")
    call = replies(bad, ai())
    r = run(case, s, Toolbox(FakeData()), [], "2026-10-17", "k", call=call)
    assert r["status"] == "ok" and r["revised"] and "failed these checks" in call.seen[1][-1]["content"]
    r2 = run(case, s, Toolbox(FakeData()), [], "2026-10-17", "k", call=replies(bad, bad))
    assert r2["status"] == "rejected" and r2["problems"] == ["numbers"]


def test_no_silent_repeats_of_ignored_advice():
    plans = [dict(day="2026-10-17", focus="prioritize_sleep", response="dismissed", outcome=None)]
    assert repeat_problem(ai(), plans, "2026-10-17")
    assert repeat_problem(ai(repeat_justification="Smaller step: 20 minutes earlier."), plans, "2026-10-17") is None
    assert repeat_problem(ai(focus_type="none"), plans, "2026-10-17") is None
    followed = [dict(plans[0], response="added", outcome="done")]
    assert repeat_problem(ai(), followed, "2026-10-17") is None


def test_bad_notes_are_dropped_not_fatal():
    _, case = setup()
    assert check_notes(dict(notes_for_tomorrow=["Check bedtime", "x", "y"]), case) == (["Check bedtime", "x"], [])
    assert check_notes(dict(notes_for_tomorrow=["HRV fell 9137 ms", "Check bedtime"]), case) == (
        ["Check bedtime"], ["numbers in notes"])
    s, case = setup()
    long_note = ai(notes_for_tomorrow=["x" * 200])
    r = run(case, s, Toolbox(FakeData()), [], "2026-10-17", "k", call=replies(long_note))
    assert r["status"] == "ok" and r["notes"] == [] and r["notes_dropped"] == ["note length"]


def test_tool_budget_forces_an_answer():
    s, case = setup()
    tool = dict(content=[dict(type="tool_use", id=f"t{i}", name="get_metric_history",
                              input=dict(metric="recovery", days=7)) for i in range(4)])
    call = replies(tool, tool, ai())                       # 8 tool calls asked, budget is 6
    r = run(case, s, Toolbox(FakeData(), allowed={"get_metric_history"}), [], "2026-10-17", "k", call=call)
    assert r["status"] == "ok" and len(r["trace"]) == 6
    last_results = call.seen[2][-1]["content"]
    assert sum(x.get("is_error", False) for x in last_results) == 2 and "Reply now" in last_results[-1]["content"]


def test_daily_agent_cannot_write_or_propose():
    s, case = setup()
    tb = Toolbox(FakeData(), allowed={"get_metric_history"})
    assert "not available" in tb.run("propose_block", {})["error"]
    assert "not available" in tb.run("remember", dict(kind="goal", text="x"))["error"]
