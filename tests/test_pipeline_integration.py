"""End-to-end run of the daily pipeline against an in-memory SQLite database, with a fake
token store, a fake mail sender and a fixed clock. No network, no Postgres.

Skipped automatically where SQLAlchemy is not installed.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy.pool import StaticPool  # noqa: E402

from src.db.models import Base, DailyPlan, Recovery, Sleep, User, UserSettings  # noqa: E402
from src.db.session import make_session_factory  # noqa: E402
from src.db.upsert import upsert  # noqa: E402
from src.ingestion.whoop_mappers import recovery_row, sleep_row  # noqa: E402
from src.pipeline.daily import DailyPipeline  # noqa: E402
from src.settings import Settings  # noqa: E402

USER = 42
TZ = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 10, 16)


class FakeStore:
    def list_users(self):
        return [str(USER)]


class OfflinePipeline(DailyPipeline):
    def sync_sources(self, user_id, run):  # no network in tests
        run.steps.append("sync skipped (test)")


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def seed(factory, nights=40):
    sleeps, recs = [], []
    for k in range(nights, 0, -1):
        d = TODAY - timedelta(days=k)
        start = datetime(d.year, d.month, d.day, 23, 0, tzinfo=TZ)
        end = start + timedelta(hours=8)
        sid = f"s{k}"
        sleeps.append(sleep_row({
            "id": sid, "user_id": USER, "start": _iso(start), "end": _iso(end), "timezone_offset": "-07:00",
            "nap": False, "score_state": "SCORED", "score": {
                "stage_summary": {"total_in_bed_time_milli": 8 * 3_600_000,
                                  "total_light_sleep_time_milli": 250 * 60_000,
                                  "total_slow_wave_sleep_time_milli": 90 * 60_000,
                                  "total_rem_sleep_time_milli": 100 * 60_000},
                "sleep_needed": {"baseline_milli": 450 * 60_000},
                "sleep_performance_percentage": 90, "sleep_efficiency_percentage": 92},
        }))
        recs.append(recovery_row({
            "cycle_id": 1000 + k, "sleep_id": sid, "user_id": USER, "score_state": "SCORED",
            "created_at": _iso(end), "updated_at": _iso(end),
            "score": {"recovery_score": 70 if k > 1 else 85, "resting_heart_rate": 55, "hrv_rmssd_milli": 60.0},
        }))
    with factory() as s:
        upsert(s, User, [dict(user_id=USER, first_name="Test", timezone="America/Los_Angeles")], ["user_id"])
        upsert(s, Sleep, sleeps, ["id"])
        upsert(s, Recovery, recs, ["cycle_id"])
        s.commit()


@pytest.fixture
def factory():
    engine = sqlalchemy.create_engine("sqlite://", poolclass=StaticPool,
                                      connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    f = make_session_factory(engine)
    seed(f)
    return f


def make_pipeline(factory, outbox, hour=11):
    return OfflinePipeline(
        session_factory=factory,
        settings=Settings(report_email_to="me@example.com"),
        whoop_store=FakeStore(),
        sender=lambda to, subject, html, text: outbox.append((to, subject, html, text)),
        clock=lambda zone: datetime(TODAY.year, TODAY.month, TODAY.day, hour, 0, tzinfo=zone),
    )


def test_send_now_emails_and_records_the_plan(factory):
    outbox = []
    run = make_pipeline(factory, outbox).run_user(str(USER), mode="now")
    assert run.outcome == "sent" and len(outbox) == 1
    to, subject, html, _ = outbox[0]
    assert to == "me@example.com" and "Recovery 85%" in subject and "RECOVERY LAB" in html
    with factory() as s:
        plan = s.get(DailyPlan, (USER, TODAY))
        assert plan is not None and plan.focus in ("none", "go_hard", "lower_intensity",
                                                   "prioritize_sleep", "recover_between")
        settings = s.get(UserSettings, USER)
        assert settings is None or settings.last_report_on is None   # a manual send never cancels the scheduled one


def test_scheduled_run_respects_time_and_sends_once(factory):
    outbox = []
    early = make_pipeline(factory, outbox, hour=8).run_user(str(USER))
    assert early.outcome == "skipped" and not outbox            # default report time is 10:00
    first = make_pipeline(factory, outbox, hour=11).run_user(str(USER))
    again = make_pipeline(factory, outbox, hour=12).run_user(str(USER))
    assert first.outcome == "sent" and again.outcome == "skipped" and len(outbox) == 1


def test_yesterdays_focus_is_checked_from_data_and_stored(factory):
    with factory() as s:
        s.add(DailyPlan(user_id=USER, day=TODAY - timedelta(days=1), focus="prioritize_sleep", score=0.7,
                        reasons=[], considered=[], block=dict(start="21:45", end="22:30", minutes=45,
                                                              title="Wind down")))
        s.commit()
    outbox = []
    make_pipeline(factory, outbox).run_user(str(USER), mode="now")
    _, _, html, text = outbox[0]
    assert "YESTERDAY" in text and "Earlier night: in bed at 23:00" in text and "Yesterday" in html
    with factory() as s:
        y = s.get(DailyPlan, (USER, TODAY - timedelta(days=1)))
        assert y.outcome == "partly" and y.outcome_detail["minutes_late"] == 30
        assert y.response is None                         # no click is not a rejection


def test_outcomes_missing_data_are_rechecked_later(factory):
    two_days_ago = TODAY - timedelta(days=2)
    with factory() as s:
        s.add(DailyPlan(user_id=USER, day=two_days_ago, focus="prioritize_sleep", score=0.7, reasons=[],
                        considered=[], block=dict(start="22:15", end="23:00", minutes=45, title="Wind down"),
                        outcome="no_data"))     # the sleep was not scored when that email went out
        s.commit()
    make_pipeline(factory, []).run_user(str(USER), mode="now")
    with factory() as s:
        assert s.get(DailyPlan, (USER, two_days_ago)).outcome == "done"   # in bed at 23:00, target 23:00


def test_wording_falls_back_and_logs_status_only(factory):
    import json as _json
    outbox = []
    p = make_pipeline(factory, outbox)
    reply = "Zebrafish advice: rest for 999 minutes."                     # invented number, unique marker word
    p.wording_call = lambda key, model, data: _json.dumps({"message": reply})
    run = p.run_user(str(USER), mode="now")
    assert run.outcome == "sent"
    assert not any("Zebrafish" in step for step in run.steps)            # never the text in logs
    assert any(step.startswith("wording: ") for step in run.steps)    # status only (template, skipped, ...)
    assert "Zebrafish" not in outbox[0][2]                               # the template went out instead


AI_PLAN = dict(focus_type="prioritize_sleep", title="Ease into an earlier night", confidence="tentative",
               headline="Recovery looks fine, so tonight is a good chance to start winding down a little earlier.",
               reasons=[dict(text="Your recovery is in a good place today.", evidence=["E1"])], counter=[],
               action=dict(type="calendar_block", title="Wind down: lights low", start="22:00", minutes=30),
               uncertainty=None, hypothesis=None)


def test_ai_plan_is_shown_and_both_engines_are_stored(factory):
    import json as _json
    outbox = []
    p = make_pipeline(factory, outbox)
    p.settings = Settings(report_email_to="me@example.com", reasoning_mode="ai")
    p.reasoning_call = lambda key, model, case: _json.dumps(AI_PLAN)
    run = p.run_user(str(USER), mode="now")
    assert "reasoning: ok" in run.steps
    assert "Ease into an earlier night" in outbox[0][2] and "reasoned by AI" in outbox[0][2]
    with factory() as s:
        plan = s.get(DailyPlan, (USER, TODAY))
        assert plan.engine == "ai" and plan.ai_status == "ok" and plan.title == "Ease into an earlier night"
        assert plan.block["start"] == "22:00" and plan.rule_focus["focus"] and plan.evidence["evidence"]


def test_rejected_ai_plan_falls_back_to_the_rules(factory):
    import json as _json
    outbox = []
    p = make_pipeline(factory, outbox)
    bad = dict(AI_PLAN, headline="Sleep 937 extra minutes tonight.")          # invented number
    p.reasoning_call = lambda key, model, case: _json.dumps(bad)
    run = p.run_user(str(USER), mode="now")
    assert "reasoning: rejected (numbers)" in run.steps
    assert "Ease into an earlier night" not in outbox[0][2]
    with factory() as s:
        plan = s.get(DailyPlan, (USER, TODAY))
        assert plan.engine == "rules" and plan.ai_status == "rejected" and plan.ai_problems == ["numbers"]


def test_active_experiment_appears_in_the_email(factory):
    from src.db.models import Experiment
    from src.experiments.design import make_schedule
    start = TODAY - timedelta(days=2)
    with factory() as s:
        s.add(Experiment(user_id=USER, preset="screens_off_30", start_day=start, nights=4, seed=5,
                         schedule=make_schedule(start, 4, 5), status="active"))
        s.commit()
    outbox = []
    make_pipeline(factory, outbox).run_user(str(USER), mode="now")
    html, text = outbox[0][2], outbox[0][3]
    assert "No screens 30 minutes before bed" in html and "night 3 of 4" in text.lower()


def test_ai_proposal_becomes_a_start_button(factory):
    import json as _json

    from src.db.models import Experiment
    outbox = []
    p = make_pipeline(factory, outbox)
    plan = dict(AI_PLAN, experiment_proposal=dict(preset="screens_off_30", why="A good moment to test a habit.",
                                                  evidence=["E1"]))
    p.reasoning_call = lambda key, model, case: _json.dumps(plan)
    p.run_user(str(USER), mode="now")
    assert "Suggested experiment" in outbox[0][2]
    with factory() as s:
        e = s.query(Experiment).one()
        assert e.status == "proposed" and e.preset == "screens_off_30" and e.reason.startswith("A good moment")
