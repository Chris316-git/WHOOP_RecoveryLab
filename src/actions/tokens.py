"""Signed, expiring action links. Pure logic, no I/O.

A token names one user, one plan day and one action, plus an expiry. It is signed with
HMAC-SHA256 under ACTION_SIGNING_KEY, so links cannot be forged or edited, and it carries
no health data. Repeated clicks are harmless: every action checks the plan's current state.

Links from older emails used accept / adjust / skip; they are still honored under the new names.
"""
import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import date

ACTIONS = ("add", "change", "dismiss", "undo", "not_useful", "adhere_yes", "adhere_no",
           "exp_start", "exp_decline", "exp_keep", "exp_extend", "exp_drop", "exp_stop", "exp_browse")
ALIASES = {"accept": "add", "adjust": "change", "skip": "dismiss"}


class InvalidToken(ValueError):
    pass


@dataclass(frozen=True)
class ActionToken:
    user_id: int
    day: date
    action: str
    expires_at: int  # Unix seconds


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig(payload: str, key: str) -> str:
    return _b64(hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest()[:16])


def sign(token: ActionToken, key: str) -> str:
    if token.action not in ACTIONS:
        raise ValueError(f"unknown action {token.action!r}")
    if not key:
        raise ValueError("ACTION_SIGNING_KEY is empty")
    payload = f"{token.user_id}|{token.day.isoformat()}|{token.action}|{token.expires_at}"
    return f"{_b64(payload.encode())}.{_sig(payload, key)}"


def verify(text: str, key: str, now: float | None = None) -> ActionToken:
    try:
        body, sig = text.split(".", 1)
        payload = _unb64(body).decode()
        user, day, action, exp = payload.split("|")
    except Exception:
        raise InvalidToken("malformed link") from None
    if not hmac.compare_digest(sig, _sig(payload, key)):
        raise InvalidToken("this link is not valid")
    token = ActionToken(int(user), date.fromisoformat(day), ALIASES.get(action, action), int(exp))
    if token.action not in ACTIONS:
        raise InvalidToken("unknown action")
    if (now if now is not None else time.time()) > token.expires_at:
        raise InvalidToken("this link has expired")
    return token
