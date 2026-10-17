from datetime import date

import pytest

from src.actions.options import slot_options
from src.actions.tokens import ActionToken, InvalidToken, sign, verify
from src.gcal.write import event_body

KEY = "test-signing-key"
DAY = date(2026, 10, 16)


def test_token_round_trip_and_tamper_protection():
    t = ActionToken(42, DAY, "add", expires_at=2_000_000_000)
    text = sign(t, KEY)
    assert verify(text, KEY, now=1_900_000_000) == t
    with pytest.raises(InvalidToken):
        verify(text, "other-key", now=1_900_000_000)
    body, sig = text.split(".")
    forged = sign(ActionToken(43, DAY, "add", 2_000_000_000), KEY).split(".")[0] + "." + sig
    with pytest.raises(InvalidToken):
        verify(forged, KEY, now=1_900_000_000)
    with pytest.raises(InvalidToken, match="expired"):
        verify(text, KEY, now=2_000_000_001)
    with pytest.raises(InvalidToken):
        verify("garbage", KEY)


def test_links_from_older_emails_still_work():
    from src.actions.tokens import _b64, _sig
    payload = f"42|{DAY.isoformat()}|skip|2000000000"
    old = f"{_b64(payload.encode())}.{_sig(payload, KEY)}"
    assert verify(old, KEY, now=1_900_000_000).action == "dismiss"


def test_slot_options_for_daytime_and_wind_down_blocks():
    block = dict(start="16:00", end="16:30", minutes=30, title="Easy movement")
    free = [dict(start="12:00", end="13:00", minutes=60), dict(start="16:00", end="20:00", minutes=240)]
    opts = slot_options(block, free, "lower_intensity")
    starts = [(o["start"], o["minutes"]) for o in opts]
    assert ("12:00", 30) in starts and ("16:00", 30) not in starts   # the original slot is not repeated
    assert any(o["minutes"] == 15 for o in opts) and len(opts) <= 4
    wind = dict(start="21:45", end="22:30", minutes=45, title="Wind down")
    assert [o["start"] for o in slot_options(wind, free, "prioritize_sleep")] == ["21:15", "22:15"]


def test_event_body_is_timezone_aware_with_reminder():
    body = event_body(DAY, dict(start="16:30", minutes=30, title="Easy movement"), "America/Los_Angeles",
                      "Take it easy today", ["3 hard days in a row"])
    assert body["start"]["dateTime"] == "2026-10-16T16:30:00-07:00"
    assert body["end"]["dateTime"] == "2026-10-16T17:00:00-07:00"
    assert body["reminders"]["overrides"][0]["minutes"] == 15 and "3 hard days" in body["description"]
    assert body["transparency"] == "opaque"
    wind = event_body(DAY, dict(start="21:45", minutes=45, title="Wind down"), "America/Los_Angeles", "x", [],
                      busy=False)
    assert wind["transparency"] == "transparent"   # a reminder, not a busy block


def test_email_buttons():
    from src.report.render import _action_buttons
    assert _action_buttons(None) == ""
    html = _action_buttons({"add": "https://x/a/1", "change": "https://x/a/2", "dismiss": "https://x/a/3"})
    assert html.count("<a href=") == 3 and "Add to calendar" in html and "Change time" in html
    assert "Dismiss" in html and "Accept" not in html and "undo" in html
    quiet = _action_buttons({"not_useful": "https://x/a/4"})       # a focus with nothing to schedule
    assert quiet.count("<a href=") == 1 and "Not useful?" in quiet and "calendar" not in quiet


def test_one_tap_page_submits_itself_but_works_without_scripts():
    from src.actions.pages import done, one_tap
    html = one_tap("/a/tok", "Adding to your calendar…", "Add to calendar",
                   dict(start="16:30", end="17:00", title="Walk"))
    assert 'method="post"' in html and ".submit()" in html and "Add to calendar</button>" in html
    result = done("Added", "On your calendar.", undo_url="/a/undo", not_useful_url="/a/nu")
    assert "Undo" in result and "wasn&#x27;t useful" in result


def test_settings_drop_quotes_pasted_from_env_files():
    from src.settings import Settings
    s = Settings.from_env({"DATABASE_URL": ' "postgresql://u:p@h/db" ', "ACTION_SIGNING_KEY": "'abc'"})
    assert s.database_url == "postgresql://u:p@h/db" and s.action_signing_key == "abc"
