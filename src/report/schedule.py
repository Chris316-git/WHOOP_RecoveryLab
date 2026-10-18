"""When to send each user's daily report. Pure logic, no I/O.

The job runs when WHOOP reports a new sleep or recovery (webhook, see src/api/webhooks.py)
and every 30 minutes as a fallback. For each user it sends at most one report per local day:
not before `report_time`, and (if `wait_for_sleep`) only once last night's sleep has been
scored by WHOOP, with `latest_time` as a deadline so a late or missing score never means no
report. With the webhook, the email arrives a minute or two after the score.
"""
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_REPORT_TIME = time(5, 0)   # earliest; the email waits for the sleep score
DEFAULT_LATEST_TIME = time(13, 0)


@dataclass(frozen=True)
class ReportSchedule:
    report_time: time = DEFAULT_REPORT_TIME
    latest_time: time = DEFAULT_LATEST_TIME
    wait_for_sleep: bool = True
    enabled: bool = True
    last_report_on: date | None = None

    @classmethod
    def from_row(cls, row) -> "ReportSchedule":
        """Build from a UserSettings row (or None); unset columns fall back to defaults."""
        if row is None:
            return cls()
        return cls(
            report_time=row.report_time or DEFAULT_REPORT_TIME,
            latest_time=row.latest_time or DEFAULT_LATEST_TIME,
            wait_for_sleep=True if row.wait_for_sleep is None else row.wait_for_sleep,
            enabled=True if row.report_enabled is None else row.report_enabled,
            last_report_on=row.last_report_on,
        )


def in_window(s: ReportSchedule, now_local: datetime) -> tuple[bool, str]:
    """Whether the job should do any work for this user right now (sync + maybe send)."""
    if not s.enabled:
        return False, "reports disabled"
    if s.last_report_on == now_local.date():
        return False, "already sent today"
    if now_local.time() < s.report_time:
        return False, f"before report time {s.report_time:%H:%M}"
    return True, "due"


def ready_to_send(s: ReportSchedule, now_local: datetime, last_night_scored: bool) -> tuple[bool, str]:
    """Called after syncing, inside the window."""
    if not s.wait_for_sleep or last_night_scored:
        return True, "ready"
    if now_local.time() >= s.latest_time:
        return True, f"sleep not scored by {s.latest_time:%H:%M}; sending anyway"
    return False, "waiting for last night's sleep to be scored"


def parse_hhmm(value: str) -> time:
    try:
        h, m = value.strip().split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        raise ValueError(f"Expected a time like 10:30, got {value!r}") from None


def resolve_timezone(chosen: str | None, calendar_tz: str | None, default: str) -> str:
    """The user's explicit choice wins; otherwise follow their Google Calendar setting."""
    return chosen or calendar_tz or default


def validate_timezone(name: str) -> str:
    """Return a valid IANA time zone name such as "Asia/Shanghai" or raise ValueError."""
    name = name.strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown time zone {name!r}. Use an IANA name such as "
                         "America/Los_Angeles, America/New_York, Europe/London or Asia/Shanghai.") from None
    return name
