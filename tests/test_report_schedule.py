from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.report.schedule import ReportSchedule, in_window, parse_hhmm, ready_to_send

Z = ZoneInfo("America/Los_Angeles")


def at(h, m=0):
    return datetime(2026, 10, 16, h, m, tzinfo=Z)


def test_not_before_report_time_and_once_per_day():
    s = ReportSchedule(report_time=time(10, 30))
    assert in_window(s, at(10, 0))[0] is False
    assert in_window(s, at(10, 30))[0] is True
    sent = ReportSchedule(report_time=time(10, 30), last_report_on=date(2026, 10, 16))
    assert in_window(sent, at(11))[0] is False
    assert in_window(ReportSchedule(enabled=False), at(11))[0] is False


def test_waits_for_sleep_score_until_deadline():
    s = ReportSchedule(report_time=time(10), latest_time=time(13))
    assert ready_to_send(s, at(10, 5), last_night_scored=False)[0] is False
    assert ready_to_send(s, at(10, 5), last_night_scored=True)[0] is True
    assert ready_to_send(s, at(13, 5), last_night_scored=False)[0] is True
    assert ready_to_send(ReportSchedule(wait_for_sleep=False), at(10, 5), False)[0] is True


def test_parse_hhmm():
    assert parse_hhmm("9:05") == time(9, 5)
    with pytest.raises(ValueError):
        parse_hhmm("noon")
