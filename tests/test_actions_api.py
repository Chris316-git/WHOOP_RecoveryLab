"""Add to calendar / Change time / Dismiss / Undo endpoints against in-memory SQLite with a fake calendar.
Skipped automatically where FastAPI or SQLAlchemy is not installed."""
from datetime import date, datetime, timezone

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.actions.service import ActionService  # noqa: E402
from src.actions.tokens import ActionToken, sign  # noqa: E402
from src.api.main import app  # noqa: E402
from src.db.models import Base, DailyPlan, User, UserSettings  # noqa: E402
from src.db.session import make_session_factory  # noqa: E402

KEY = "test-key"
USER = 7
DAY = date(2026, 10, 16)
BLOCK = dict(start="16:30", end="17:00", minutes=30, title="Hard session: intervals")


class FakeCalendar:
    def __init__(self):
        self.events, self.calls = {}, []

    def add(self, user_id, day, tz, block, focus, title, reasons, calendar_id):
        event_id = f"evt-{len(self.calls) + 1}"
        self.calls.append(("add", block["start"]))
        self.events[event_id] = block["start"]
        return "cal-123", event_id

    def move(self, user_id, calendar_id, event_id, day, tz, block, focus, title, reasons):
        self.calls.append(("move", block["start"]))
        self.events[event_id] = block["start"]

    def remove(self, user_id, calendar_id, event_id):
        self.calls.append(("remove", event_id))
        self.events.pop(event_id, None)


@pytest.fixture
def setup():
    engine = sqlalchemy.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        s.add(User(user_id=USER, first_name="T"))
        for d in (DAY, date(2026, 10, 17)):
            s.add(DailyPlan(user_id=USER, day=d, focus="go_hard", score=0.8, reasons=["recovery is green"],
                            block=BLOCK, considered=[], timezone="America/Los_Angeles"))
        s.commit()
    calendar = FakeCalendar()
    app.state.action_service = ActionService(factory, calendar=calendar,
                                             clock=lambda: datetime(2026, 10, 16, 17, 0, tzinfo=timezone.utc))
    app.state.signing_key = KEY
    yield TestClient(app), factory, calendar
    del app.state.action_service


def link(action, day=DAY):
    return "/a/" + sign(ActionToken(USER, day, action, 4_000_000_000), KEY)


def follow_up(html):
    """The Undo / Not useful form actions on a result page."""
    import re
    return re.findall(r'action="(/a/[^"]+)"', html)


def test_get_never_changes_anything_and_one_post_adds(setup):
    client, factory, calendar = setup
    r = client.get(link("add"))
    assert r.status_code == 200 and ".submit()" in r.text and r.headers["cache-control"] == "no-store"
    with factory() as s:
        assert s.get(DailyPlan, (USER, DAY)).response is None and not calendar.calls
    r = client.post(link("add"))
    assert r.status_code == 200 and "Added to your calendar" in r.text and calendar.calls == [("add", "16:30")]
    with factory() as s:
        plan = s.get(DailyPlan, (USER, DAY))
        assert (plan.response, plan.calendar_status, plan.event_id) == ("added", "scheduled", "evt-1")
        assert plan.outcome is None                      # scheduled is not the same as done
        assert s.get(UserSettings, USER).rl_calendar_id == "cal-123"
    again = client.post(link("add"))
    assert "Already done" in again.text and len(calendar.calls) == 1


def test_undo_removes_the_event(setup):
    client, factory, calendar = setup
    undo_url = follow_up(client.post(link("add")).text)[0]
    r = client.post(undo_url)
    assert "Undone" in r.text and calendar.events == {}
    with factory() as s:
        plan = s.get(DailyPlan, (USER, DAY))
        assert plan.response is None and plan.calendar_status == "removed"


def test_change_time_moves_an_added_event(setup):
    client, factory, calendar = setup
    client.post(link("add"))
    page = client.get(link("change")).text
    assert "Pick another time" in page or "No other free time" in page


def test_dismiss_needs_no_reason_and_not_useful_is_optional(setup):
    client, factory, calendar = setup
    day2 = date(2026, 10, 17)
    r = client.post(link("dismiss", day2))
    assert r.status_code == 200 and "Dismissed" in r.text and not calendar.calls
    with factory() as s:
        assert s.get(DailyPlan, (USER, day2)).response == "dismissed"
    undo_url, not_useful_url = follow_up(r.text)
    client.post(not_useful_url)
    with factory() as s:
        assert s.get(DailyPlan, (USER, day2)).response == "not_useful"


def test_old_links_and_invalid_links(setup):
    client, factory, _ = setup
    from src.actions.tokens import _b64, _sig
    payload = f"{USER}|{DAY.isoformat()}|accept|4000000000"          # an older email's Accept link
    assert client.post(f"/a/{_b64(payload.encode())}.{_sig(payload, KEY)}").status_code == 200
    with factory() as s:
        assert s.get(DailyPlan, (USER, DAY)).response == "added"
    assert client.get("/a/not-a-token").status_code == 400
    forged = "/a/" + sign(ActionToken(USER, DAY, "add", 4_000_000_000), "wrong-key")
    assert client.post(forged).status_code == 400


def test_experiment_answer_is_recorded(setup):
    from src.db.models import Experiment, ExperimentDay
    from src.experiments.design import make_schedule
    client, factory, _ = setup
    with factory() as s:
        s.add(Experiment(id=1, user_id=USER, preset="screens_off_30", start_day=DAY, nights=4, seed=1,
                         schedule=make_schedule(DAY, 4, 1), status="active"))
        s.commit()
    assert "Saving your answer" in client.get(link("adhere_yes")).text
    r = client.post(link("adhere_yes"))
    assert "Answer saved" in r.text
    client.post(link("adhere_no"))                                  # changing the answer overwrites it
    with factory() as s:
        assert s.get(ExperimentDay, (1, DAY)).adherence == "no"
