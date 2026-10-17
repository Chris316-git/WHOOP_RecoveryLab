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
        assert s.get(UserSettings, USER).last_report_on == TODAY


def test_scheduled_run_respects_time_and_sends_once(factory):
    outbox = []
    early = make_pipeline(factory, outbox, hour=8).run_user(str(USER))
    assert early.outcome == "skipped" and not outbox            # default report time is 10:00
    first = make_pipeline(factory, outbox, hour=11).run_user(str(USER))
    again = make_pipeline(factory, outbox, hour=12).run_user(str(USER))
    assert first.outcome == "sent" and again.outcome == "skipped" and len(outbox) == 1
