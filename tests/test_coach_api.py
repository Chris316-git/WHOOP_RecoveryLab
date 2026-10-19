"""Coach endpoints against in-memory SQLite, a fake model and a fake calendar.
Skipped automatically where FastAPI or SQLAlchemy is not installed."""
from datetime import date, timezone

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.actions.tokens import ActionToken, sign  # noqa: E402
from src.api.main import app  # noqa: E402
from src.coach.service import CoachService  # noqa: E402
from src.db.models import Base, User, UserSettings  # noqa: E402
from src.db.session import make_session_factory  # noqa: E402
from tests.test_coach import NOW, FakeData  # noqa: E402

KEY, USER = "test-key", 7


class FakeCalendar:
    def __init__(self):
        self.calls = []

    def add(self, user_id, day, tz, block, focus, title, reasons, calendar_id):
        self.calls.append(("add", day.isoformat(), block["start"], focus))
        return "cal-1", "evt-1"

    def remove(self, user_id, calendar_id, event_id):
        self.calls.append(("remove", event_id))


def fake_model():
    replies = [
        dict(content=[dict(type="tool_use", id="t1", name="propose_block",
                           input=dict(day="today", start="17:30", minutes=30, title="Easy walk", kind="easy",
                                      why="Short and easy."))]),
        dict(content=[dict(type="text", text="How about an easy walk at 17:30?")]),
    ]
    return lambda messages: replies.pop(0)


@pytest.fixture
def client():
    engine = sqlalchemy.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        s.add(User(user_id=USER, first_name="T", timezone="America/Los_Angeles"))
        s.commit()
    calendar = FakeCalendar()
    app.state.coach_service = CoachService(factory, KEY, "", calendar=calendar, call=fake_model(),
                                           clock=lambda: NOW.astimezone(timezone.utc),
                                           data_factory=lambda uid, tz, now: FakeData())
    yield TestClient(app), factory, calendar
    del app.state.coach_service


def url(action="coach", user=USER):
    return "/coach/" + sign(ActionToken(user, date(2026, 10, 18), action, 4_000_000_000), KEY)


def test_chat_propose_add_and_undo(client):
    c, factory, calendar = client
    assert c.get(url()).status_code == 200 and "COACH" in c.get(url()).text
    assert c.get(url("add")).status_code == 403
    r = c.post(url() + "/message", json=dict(history=[dict(role="user", content="more energy please")])).json()
    assert "17:30" in r["reply"] and len(r["proposals"]) == 1
    token = r["proposals"][0]["token"]
    added = c.post(url() + "/add", json=dict(token=token)).json()
    assert added["ok"] and calendar.calls == [("add", "2026-10-18", "17:30", "coach")]
    with factory() as s:
        assert s.get(UserSettings, USER).rl_calendar_id == "cal-1"
    other = "/coach/" + sign(ActionToken(8, date(2026, 10, 18), "coach", 4_000_000_000), KEY)
    assert c.post(other + "/add", json=dict(token=token)).json()["ok"] is False   # another user's link
    assert c.post(url() + "/undo", json=dict(token=added["undo"])).json()["ok"]
    assert calendar.calls[-1] == ("remove", "evt-1")


def test_memory_is_saved_and_can_be_forgotten(client):
    from src.memory import store
    c, factory, _ = client
    with factory() as s:
        m = store.add(s, USER, "goal", "Fall asleep before 23:30")
        assert store.add(s, USER, "goal", "fall asleep before 23:30")["id"] == m["id"]     # no duplicates
    from src.coach.service import seal
    token = seal(dict(user=USER, memory=m["id"], exp=4_000_000_000), KEY)
    assert c.post(url() + "/forget", json=dict(token=token)).json()["ok"]
    with factory() as s:
        assert store.active(s, USER) == []
    assert c.post(url() + "/forget", json=dict(token=token)).json()["ok"] is False


def test_bad_history_is_rejected(client):
    c, _, _ = client
    assert c.post(url() + "/message", json=dict(history=[])).status_code == 400
