import json

from src.llm.wording import check, word_focus, wording_input

SUMMARY = dict(
    metrics=[dict(key="recovery_score", value=54)], recovery_zone="yellow",
    focus=dict(focus="lower_intensity", title="Take it easy today", confidence="moderate",
               headline="A lighter day is probably the better call.",
               reasons=["HRV has been below your normal range this week (95.2 ms vs 97.7-117.5)",
                        "yesterday was a hard day (strain 15.5)"],
               counter=["sleep performance was 80%, normal for you"],
               block=dict(start="16:00", end="16:30", minutes=30, title="Golf: range or short-game practice")),
    yesterday=dict(text="it ended up a hard day (strain 15.5)"),
)


def fake(reply):
    return lambda key, model, data: json.dumps({"message": reply})


def test_input_is_compact_and_computed():
    data = wording_input(SUMMARY)
    assert data["suggested_block"]["start"] == "16:00" and data["recovery_percent"] == 54
    assert set(data) <= {"focus", "confidence", "template_headline", "reasons", "pointing_the_other_way",
                         "recovery_percent", "recovery_zone", "suggested_block", "yesterday"}
    assert wording_input(dict(SUMMARY, focus=dict(focus="none", reasons=[]))) is None


def test_good_reply_is_used():
    msg = ("Your HRV has been running low and yesterday was a hard day, so keep today light. "
           "Some range practice at 16:00 would fit nicely.")
    assert word_focus(SUMMARY, "key", call=fake(msg)) == (msg, "llm")


def test_invented_numbers_fall_back_to_the_template():
    msg, status = word_focus(SUMMARY, "key", call=fake("Your HRV dropped 12% so rest for 45 minutes."))
    assert msg is None and status == "template (failed numbers check)"


def test_other_failures_fall_back():
    assert word_focus(SUMMARY, "", call=fake("x"))[1] == "template (no API key)"
    assert word_focus(SUMMARY, "key", call=lambda *a: "not json")[1].startswith("template (")

    def boom(*a):
        raise TimeoutError

    assert word_focus(SUMMARY, "key", call=boom)[1] == "template (TimeoutError)"
    data = wording_input(SUMMARY)
    assert check("This could be a sign of illness, see a doctor.", data) == "wording"
    assert check("x" * 500, data) == "length"


def test_email_uses_the_message_when_present():
    from src.report.render import _focus
    f = dict(SUMMARY["focus"], message="Keep today light; range practice at 16:00 fits.")
    html = _focus(dict(SUMMARY, focus=f))
    assert "range practice at 16:00 fits" in html and "probably the better call" not in html
