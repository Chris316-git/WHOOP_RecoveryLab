"""WHOOP webhooks: send the morning email as soon as last night's sleep is scored.

WHOOP calls POST /webhooks/whoop when a sleep, recovery or workout is created or updated.
The web host only checks the signature and starts the daily GitHub Actions workflow, which
syncs, checks that last night is scored, and sends the email if it is due. The work stays in
GitHub Actions because the free web host blocks outgoing email, and one queue for every run
(webhook, schedule, manual) means two syncs never race on WHOOP's rotating refresh token.

Signature (developer.whoop.com/docs/developing/webhooks): base64(HMAC-SHA256(client secret,
timestamp header + raw body)) must equal the X-WHOOP-Signature header. Pure logic, except
`dispatch`, which takes the HTTP call as an argument.
"""
import base64
import hashlib
import hmac
import json
from collections.abc import Callable

# Recovery is what the email waits for; sleep comes first and is a harmless early check.
TRIGGER_EVENTS = {"recovery.updated", "sleep.updated"}
WORKFLOW_FILE = "daily.yml"


def valid_signature(secret: str, timestamp: str | None, body: bytes, signature: str | None) -> bool:
    if not secret or not timestamp or not signature:
        return False
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature.strip())


def parse_event(body: bytes) -> dict | None:
    try:
        event = json.loads(body)
    except ValueError:
        return None
    return event if isinstance(event, dict) and "type" in event else None


def should_dispatch(event: dict) -> bool:
    return event.get("type") in TRIGGER_EVENTS


def dispatch(token: str, repo: str, post: Callable[..., object], ref: str = "main") -> int:
    """Start the daily workflow in scheduled mode (it still decides whether the email is due).
    Returns the HTTP status (204 on success)."""
    response = post(
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        json={"ref": ref, "inputs": {"trigger": "whoop"}},
        timeout=20,
    )
    return response.status_code
