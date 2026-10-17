"""Turn today's computed focus into a short, friendly message. The LLM chooses words only.

Guardrails:

* Input is structured and already computed: the focus, its reasons, the suggested block and
  yesterday's line. No raw records, calendar events, names or email addresses are sent.
* Every number in the reply must appear in that input (the numeric consistency check), the
  reply must be short, and it must not use diagnostic or alarming language.
* Any failure (no API key, timeout, bad JSON, a failed check) falls back to the template
  headline, so the email always goes out and never says something the code did not compute.
"""
import json
import re
from collections.abc import Callable

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"
MAX_CHARS = 420
BANNED = ("diagnos", "disease", "illness", "disorder", "dangerous", "emergency", "doctor", "you must", "guarantee")

SYSTEM = """You write the opening lines of a personal daily health email.
You receive today's recommendation as JSON. Everything in it was computed from the reader's own wearable data.

Write 2 or 3 short sentences, 60 words at most, in a warm, plain and calm tone, addressed to the reader as "you":
- say what to do today and the main reason, in everyday words;
- if there is a suggested block, mention its time exactly as given (24-hour, e.g. 16:00);
- if "yesterday" is present, you may mention it briefly as a fact, never as proof that something worked;
- match the confidence: "high" can be direct; "moderate" or "tentative" should sound like a suggestion.

Rules: use only numbers that appear in the input, copied exactly; do not add facts, causes or medical claims;
no diagnoses, no alarm, no emojis, no greeting, no sign-off.
Reply with JSON only: {"message": "..."}"""

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def wording_input(summary: dict) -> dict | None:
    """The compact, already computed facts the LLM may use. None when there is nothing to word."""
    f = summary.get("focus") or {}
    if f.get("focus") in (None, "none") or not f.get("reasons"):
        return None
    block = f.get("block")
    data = dict(
        focus=f["title"],
        confidence=f.get("confidence"),
        template_headline=f.get("headline"),
        reasons=f["reasons"][:4],
        pointing_the_other_way=(f.get("counter") or [])[:2],
        recovery_percent=summary["metrics"][0]["value"],
        recovery_zone=summary.get("recovery_zone"),
    )
    if block:
        data["suggested_block"] = dict(start=block["start"], end=block["end"], what=block["title"])
    y = summary.get("yesterday")
    if y:
        data["yesterday"] = f"{y['text']}"
    return data


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUMBER.findall(text)}


def check(message: str, data: dict) -> str | None:
    """Why the message is rejected, or None if it passes."""
    if not message or len(message) > MAX_CHARS:
        return "length"
    lowered = message.lower()
    if any(word in lowered for word in BANNED):
        return "wording"
    unknown = _numbers(message) - _numbers(json.dumps(data))
    if unknown:
        return "numbers"
    return None


def call_claude(api_key: str, model: str, data: dict, timeout: float = 30.0) -> str:
    """One Messages API call; returns the reply text. Raises on any HTTP or format problem."""
    import httpx
    resp = httpx.post(API_URL, timeout=timeout, headers={
        "x-api-key": api_key, "anthropic-version": API_VERSION, "content-type": "application/json",
    }, json={
        "model": model,
        "max_tokens": 2000,   # room for adaptive thinking; the reply itself is short
        "system": SYSTEM,
        "messages": [{"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
    })
    resp.raise_for_status()
    return "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")


def _parse(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    return str(json.loads(text[start:end + 1])["message"]).strip()


def word_focus(summary: dict, api_key: str, model: str = DEFAULT_MODEL,
               call: Callable[[str, str, dict], str] | None = None) -> tuple[str | None, str]:
    """(message or None, status). The status is safe to log: it never contains the text."""
    data = wording_input(summary)
    if data is None:
        return None, "skipped (no focus)"
    if not api_key:
        return None, "template (no API key)"
    try:
        message = _parse((call or call_claude)(api_key, model, data))
    except Exception as exc:
        return None, f"template ({type(exc).__name__})"
    problem = check(message, data)
    if problem:
        return None, f"template (failed {problem} check)"
    return message, "llm"
