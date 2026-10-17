from datetime import date, datetime, timedelta, timezone

from src.planner.habits import activity_profile, category, easy_activity, hard_activity

TODAY = date(2026, 10, 17)


def workout(days_ago, sport, hour_utc, minutes, strain, offset="-07:00"):
    start = datetime(2026, 10, 17, hour_utc, 0, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return dict(sport_name=sport, start=start, end=start + timedelta(minutes=minutes),
                timezone_offset=offset, strain=strain)


def test_categories():
    assert category("running") == "endurance" and category("weightlifting") == "strength"
    assert category("tennis") == "sport" and category("yoga") == "easy" and category("sauna") == "other"


def test_profile_learns_activity_duration_and_local_time():
    rows = [workout(d, "running", 14, 50, 12.0) for d in (2, 5, 9, 12, 16)]       # 07:00 local (UTC-7)
    rows += [workout(3, "weightlifting", 1, 60, 9.0)]                             # only once: not a habit
    rows += [workout(d, "Activity", 15, 30, 5.0) for d in (1, 4, 8)]              # generic: ignored
    rows += [workout(70, "running", 14, 50, 12.0)]                                # too old
    p = activity_profile(rows, TODAY)
    assert [s["sport"] for s in p["sports"]] == ["running"]
    run = p["sports"][0]
    assert run["sessions"] == 5 and run["minutes"] == 50 and run["usual_start"] == 7 * 60


def test_easy_and_hard_versions_follow_your_activity():
    p = activity_profile([workout(d, "running", 14, 50, 12.0) for d in (2, 5, 9, 12)], TODAY)
    easy, hard = easy_activity(p), hard_activity(p)
    assert easy["title"].startswith("Easy running") and easy["minutes"] == 30          # 60% of 50, rounded
    assert easy["prefer"] == (6 * 60 + 30, 8 * 60) and "running 4 times" in easy["basis"]
    assert hard["title"].startswith("Hard running") and hard["minutes"] == 50
    yoga = activity_profile([workout(d, "yoga", 2, 45, 3.0) for d in (1, 3, 6)]
                            + [workout(d, "tennis", 1, 90, 14.0) for d in (2, 4, 7, 9)], TODAY)
    assert easy_activity(yoga)["title"] == "Yoga, as usual"                 # an easy habit wins on easy days
    assert hard_activity(yoga)["title"].startswith("Tennis")                # never yoga as the hard session


def test_no_history_falls_back_to_generic_blocks():
    assert activity_profile([], TODAY) is None
    assert easy_activity(None)["title"] == "Easy movement: walk or mobility"
    assert hard_activity(None)["minutes"] == 60


def test_walking_is_not_your_sport_and_does_not_set_the_time():
    rows = [workout(d, "walking", 2, 40, 6.0) for d in range(1, 15)]          # many (often automatic) walks
    rows += [workout(d, "golf", 18, 240, 11.0) for d in (2, 9)]               # two rounds, 11:00 local
    p = activity_profile(rows, TODAY)
    easy, hard = easy_activity(p), hard_activity(p)
    assert easy["title"] == "Golf: range or short-game practice" and easy["minutes"] == 45
    assert hard["title"] == "Golf: a full round" and hard["minutes"] == 240
    walks_only = activity_profile([workout(d, "walking", 2, 40, 6.0) for d in range(1, 6)], TODAY)
    walk = easy_activity(walks_only)
    assert walk["prefer"] is None and walk["latest_end"] == 20 * 60           # afternoon, never late


def test_listed_activities_come_first_and_time_is_learned():
    rows = [workout(d, "running", 14, 50, 12.0) for d in (2, 5, 9, 12)]       # 07:00 local
    rows += [workout(d, "yoga", 1, 45, 3.0) for d in (3, 10)]                 # 18:00 local
    p = activity_profile(rows, TODAY, preferred_sports=["yoga"])
    easy = easy_activity(p)
    assert easy["title"] == "Yoga, as usual" and easy["prefer"] == (17 * 60 + 30, 19 * 60)
    assert "You listed yoga" in easy["basis"] and "18:00" in easy["basis"]
    assert hard_activity(p)["title"].startswith("Hard running")              # yoga is never the hard session
