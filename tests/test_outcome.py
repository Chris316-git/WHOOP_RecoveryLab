from datetime import date, datetime

import pandas as pd

from src.feedback.outcome import evaluate

DAY = date(2026, 10, 15)


def panel(load=None, sleep_start=None, rec_before=41, rec_after=64):
    idx = [date(2026, 10, 14), DAY]
    return pd.DataFrame({"load": [12.0, load], "sleep_start_local": [None, sleep_start],
                         "recovery_score": [rec_before, rec_after]}, index=idx)


def test_take_it_easy_is_checked_from_strain():
    plan = dict(focus="lower_intensity", title="Take it easy today")
    done = evaluate(plan, panel(load=8.2), DAY)
    assert done["outcome"] == "done" and "strain 8.2" in done["text"]
    assert (done["recovery_before"], done["recovery_after"]) == (41, 64)
    assert evaluate(plan, panel(load=12.0), DAY)["outcome"] == "partly"
    assert evaluate(plan, panel(load=15.5), DAY)["outcome"] == "not_done"
    assert evaluate(plan, panel(load=None), DAY)["outcome"] == "no_data"


def test_hard_session_is_the_mirror_image():
    plan = dict(focus="go_hard")
    assert evaluate(plan, panel(load=15.0), DAY)["outcome"] == "done"
    assert evaluate(plan, panel(load=6.0), DAY)["outcome"] == "not_done"


def test_sleep_focus_compares_bedtime_with_target_across_midnight():
    plan = dict(focus="prioritize_sleep", block=dict(start="21:45", end="22:30", minutes=45))
    on_time = evaluate(plan, panel(sleep_start=datetime(2026, 10, 15, 22, 40)), DAY)
    assert on_time["outcome"] == "done" and on_time["detail"]["bedtime"] == "22:40"
    late = evaluate(plan, panel(sleep_start=datetime(2026, 10, 16, 0, 10)), DAY)   # after midnight
    assert late["outcome"] == "not_done" and late["detail"]["minutes_late"] == 100
    moved = dict(plan, final_block=dict(start="22:15", end="23:00", minutes=45))  # user changed the time
    assert evaluate(moved, panel(sleep_start=datetime(2026, 10, 15, 23, 5)), DAY)["outcome"] == "done"


def test_unmeasurable_focus_is_only_reported_when_scheduled():
    plan = dict(focus="recover_between")
    assert evaluate(plan, panel(), DAY) is None
    assert evaluate(dict(plan, calendar_status="scheduled"), panel(), DAY)["outcome"] == "unmeasured"
    assert evaluate(dict(focus="none"), panel(), DAY) is None


def test_email_line_states_facts_without_claiming_cause():
    from src.report.render import render_text, yesterday_text
    y = evaluate(dict(focus="lower_intensity", title="Take it easy today"), panel(load=8.2), DAY)
    line = yesterday_text({"yesterday": y})
    assert line == "Take it easy: you kept it light (strain 8.2). Recovery 41% then, 64% today."
    assert "because" not in line and "helped" not in line
    assert render_text is not None
