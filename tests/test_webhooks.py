import base64
import hashlib
import hmac
import json

import pytest

from src.api.webhooks import dispatch, parse_event, should_dispatch, valid_signature

SECRET = "client-secret"


def sign(ts: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), ts.encode() + body, hashlib.sha256).digest()).decode()


def test_signature_matches_whoop_scheme():
    body = json.dumps({"user_id": 10129, "id": "a-uuid", "type": "recovery.updated", "trace_id": "t"}).encode()
    ts = "1760790000000"
    assert valid_signature(SECRET, ts, body, sign(ts, body))
    assert not valid_signature(SECRET, ts, body + b" ", sign(ts, body))      # body changed
    assert not valid_signature(SECRET, "1760790000001", body, sign(ts, body))  # timestamp changed
    assert not valid_signature("", ts, body, sign(ts, body))                 # not configured: refuse
    assert not valid_signature(SECRET, None, body, None)


def test_only_sleep_and_recovery_start_a_run():
    assert should_dispatch({"type": "recovery.updated"}) and should_dispatch({"type": "sleep.updated"})
    assert not should_dispatch({"type": "workout.updated"}) and not should_dispatch({"type": "sleep.deleted"})
    assert parse_event(b"not json") is None and parse_event(b"[]") is None


def test_dispatch_starts_the_workflow_in_scheduled_mode():
    calls = []

    class R:
        status_code = 204

    def post(url, **kw):
        calls.append((url, kw))
        return R()

    assert dispatch("tok", "me/repo", post) == 204
    url, kw = calls[0]
    assert url == "https://api.github.com/repos/me/repo/actions/workflows/daily.yml/dispatches"
    assert kw["json"] == {"ref": "main", "inputs": {"trigger": "whoop"}}
    assert kw["headers"]["Authorization"] == "Bearer tok"


def test_endpoint_checks_signature_and_answers_fast():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from src.api.main import app
    started = []
    app.state.webhook_secret, app.state.webhook_start = SECRET, lambda: started.append(1)
    client = TestClient(app)
    body = json.dumps({"user_id": 1, "id": "x", "type": "recovery.updated", "trace_id": "t"}).encode()
    ts = "1760790000000"
    bad = client.post("/webhooks/whoop", content=body, headers={"X-WHOOP-Signature-Timestamp": ts,
                                                                  "X-WHOOP-Signature": "nope"})
    assert bad.status_code == 401 and started == []
    ok = client.post("/webhooks/whoop", content=body, headers={"X-WHOOP-Signature-Timestamp": ts,
                                                                 "X-WHOOP-Signature": sign(ts, body)})
    assert ok.status_code == 204 and started == [1]
    workout = json.dumps({"user_id": 1, "id": "x", "type": "workout.updated"}).encode()
    client.post("/webhooks/whoop", content=workout, headers={"X-WHOOP-Signature-Timestamp": ts,
                                                              "X-WHOOP-Signature": sign(ts, workout)})
    assert started == [1]
    del app.state.webhook_secret, app.state.webhook_start
