import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.coach import tools as T
from src.coach.agent import Toolbox, chat, check_reply, clean_history
from src.coach.service import seal, unseal

TZ = "America/Los_Angeles"
Z = ZoneInfo(TZ)
TODAY = date(2026, 10, 18)
NOW = datetime(2026, 10, 18, 9, 30, tzinfo=Z)


def panel():
    days = [TODAY - timedelta(days=k) for k in range(30, 0, -1)]
    return pd.DataFrame({
        "recovery_score": [60.0 + (i % 5) * 5 for i in range(len(days))],
        "total_sleep_min": [420.0] * len(days),
        "load": [15.0 if i % 3 == 0 else 8.0 for i in range(len(days))],
        "sleep_start_local": [pd.Timestamp(datetime(d.year, d.month, d.day, 23, 30)) for d in days],
    }, index=pd.Index(days, name="day"))


EVENTS = [dict(start=datetime(2026, 10, 18, 10, 0, tzinfo=Z), end=datetime(2026, 10, 18, 17, 0, tzinfo=Z),
               attendee_count=1)]
CASE = dict(evidence=[dict(id="E1", topic="today", text="Recovery today: 54% (yellow zone).")],
            constraints=dict(hard_session_allowed=False, usual_bedtime="23:30"), today_focus="Take it easy today")


class FakeData:
    tz, now = TZ, NOW

    def panel(self):
        return panel()

    def workouts(self):
        return [dict(sport_name="Golf", start=datetime(2026, 10, d, 20, 0, tzinfo=ZoneInfo("UTC")),
                     timezone_offset="-07:00", strain=10.0) for d in (3, 6, 9, 12, 15)]

    def events(self, day):
        return EVENTS if day == TODAY else []

    def latest_case(self):
        return TODAY.isoformat(), CASE

    def __init__(self):
        self.saved = []

    def memories(self):
        return [dict(id=i + 1, **m) for i, m in enumerate(self.saved)]

    def save_memory(self, kind, text):
        if kind not in ("goal", "preference", "constraint", "correction") or not text:
            return None
        self.saved.append(dict(kind=kind, text=text))
        return dict(id=len(self.saved), kind=kind, text=text)

    def recent_plans(self, days):
        return [dict(day="2026-10-17", focus="prioritize_sleep", title="Protect your sleep tonight",
                     block=dict(start="22:15", end="23:00", title="Wind down"), response="dismissed",
                     outcome="not_done", agent_notes=["Bedtime drifting later."])]


def test_history_is_dated_by_the_morning_and_bedtime_is_a_clock():
    h = T.metric_history(panel(), "recovery", 7, TODAY)
    assert h["values"][-1]["date"] == TODAY.isoformat() and h["days_with_data"] == 7
    b = T.metric_history(panel(), "bedtime", 7, TODAY)
    assert b["average"] == "23:30" and "lowest" not in b
    assert "error" in T.metric_history(panel(), "weight", 7, TODAY)


def test_compare_groups_and_small_groups():
    c = T.compare(panel(), [], "recovery", "after_hard_days", TODAY)
    assert c["group_a"]["days"] >= 3 and "difference" in c and "not proof" in c["note"]
    golf = T.compare(panel(), FakeData().workouts(), "sleep_hours", "after_activity", TODAY, sport="golf")
    assert golf["group_a"]["days"] == 5 and golf["difference"] == 0.0
    assert "error" in T.compare(panel(), [], "recovery", "after_activity", TODAY)


def test_block_checks():
    w = T.free_time(EVENTS, TODAY, TZ, NOW)["free_windows"]
    assert [x["start"] for x in w] == ["09:30", "17:00"]
    ok = T.check_block(TODAY, "17:30", 30, "Easy walk", "easy", w, NOW, hard_allowed=False)
    assert ok == []
    assert "start is in the past" in T.check_block(TODAY, "08:00", 30, "Walk", "easy", w, NOW, True)
    assert any("free window" in p for p in T.check_block(TODAY, "12:00", 30, "Walk", "easy", w, NOW, True))
    assert any("hard session" in p for p in T.check_block(TODAY, "17:30", 45, "Sprint intervals", "other", w, NOW,
                                                         hard_allowed=False))
    assert T.check_block(TODAY, "22:45", 45, "Wind down: lights low", "wind_down", w, NOW, False) == []


def _tool(name, args, i):
    return dict(type="tool_use", id=f"t{i}", name=name, input=args)


def scripted(*replies):
    replies = list(replies)
    seen = []

    def call(messages):
        seen.append(json.loads(json.dumps(messages, default=str)))
        return replies.pop(0)
    call.seen = seen
    return call


def test_agent_uses_tools_proposes_and_checks_numbers():
    call = scripted(
        dict(content=[_tool("get_today", {}, 1), _tool("get_free_time", {"day": "today"}, 2)]),
        dict(content=[_tool("propose_block", dict(day="today", start="17:30", minutes=30, title="Easy walk",
                                                  kind="easy", why="Recovery is 54% today."), 3)]),
        dict(content=[dict(type="text", text="Recovery is 54% today, so I suggest an easy walk at 17:30.")]),
    )
    out = chat([dict(role="user", content="I want more energy")], Toolbox(FakeData()), "key", call=call)
    assert out["checked"] and out["tools_used"] == ["get_today", "get_free_time", "propose_block"]
    assert out["proposals"][0]["end"] == "18:00"
    tool_results = call.seen[1][-1]["content"]
    assert tool_results[0]["type"] == "tool_result" and "E1" in tool_results[0]["content"]


def test_invented_numbers_get_one_retry_then_a_flag():
    call = scripted(dict(content=[dict(type="text", text="Your HRV dropped 37 percent.")]),
                    dict(content=[dict(type="text", text="Your HRV dropped 37 percent.")]))
    out = chat([dict(role="user", content="hi")], Toolbox(FakeData()), "key", call=call)
    assert not out["checked"] and "automatic check" in call.seen[1][-1]["content"]
    fixed = scripted(dict(content=[dict(type="text", text="You are under-recovered.")]),
                     dict(content=[dict(type="text", text="Let me look at your data first.")]))
    assert chat([dict(role="user", content="hi")], Toolbox(FakeData()), "key", call=fixed)["checked"]


def test_unsafe_proposal_is_refused_by_code():
    tb = Toolbox(FakeData())
    r = tb.run("propose_block", dict(day="today", start="17:30", minutes=60, title="Hard session: intervals",
                                     kind="hard", why="x"))
    assert r["ok"] is False and tb.proposals == []
    assert tb.run("nope", {})["error"].startswith("unknown")


def test_history_cleaning_and_reply_check():
    h = clean_history([dict(role="assistant", content="hello"), dict(role="user", content="a"),
                       dict(role="user", content="b"), dict(role="system", content="x"), dict(role="user", content=5)])
    assert h == [dict(role="user", content="a\nb")]
    assert check_reply("Sleep 7.5 hours, 2 tips", ["sleep 7.5"]) == []
    assert check_reply("take a supplement", []) == ["words that are not allowed: supplement"]


def test_sealed_proposals_cannot_be_edited_or_reused_late():
    token = seal(dict(user=1, start="17:30", exp=2_000_000_000), "k")
    assert unseal(token, "k", now=0)["start"] == "17:30"
    body, sig = token.split(".")
    for bad in (body[:-2] + "AA." + sig, token + "x"):
        try:
            unseal(bad, "k", now=0)
            raise AssertionError("accepted a tampered token")
        except ValueError:
            pass
    try:
        unseal(token, "k", now=3_000_000_000)
        raise AssertionError("accepted an expired token")
    except ValueError:
        pass


def test_proposal_respects_a_control_night():
    class Control(FakeData):
        def latest_case(self):
            return TODAY.isoformat(), dict(CASE, constraints=dict(hard_session_allowed=True,
                                                                  experiment_tonight="control",
                                                                  experiment_conflict_words=["screen"]))
    r = Toolbox(Control()).run("propose_block", dict(day="today", start="22:30", minutes=30,
                                                     title="Wind down, no screens", kind="wind_down", why="x"))
    assert r["ok"] is False and "comparison night" in r["problems"][0]


def test_coach_remembers_corrections_and_reads_history():
    data = FakeData()
    call = scripted(
        dict(content=[_tool("get_recent_plans", {"days": 3}, 1),
                      _tool("remember", dict(kind="correction", text="Evening wind-downs at 22:15 are too early"), 2)]),
        dict(content=[dict(type="text", text="Got it, I saved that 22:15 is too early for you.")]))
    out = chat([dict(role="user", content="22:15 is way too early for me")], Toolbox(data), "k", call=call)
    assert out["remembered"][0]["kind"] == "correction" and out["checked"]
    plans = json.loads(call.seen[1][-1]["content"][0]["content"])["plans"]
    assert plans[0]["response"] == "dismissed" and plans[0]["agent_notes"] == ["Bedtime drifting later."]
    assert Toolbox(data).run("get_memory", {})["memories"][0]["text"].startswith("Evening")
    assert Toolbox(data).run("remember", dict(kind="diagnosis", text="x"))["ok"] is False
