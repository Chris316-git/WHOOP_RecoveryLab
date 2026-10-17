"""What kind of activity to suggest, learned from the user's own workout history. Pure logic.

Instead of suggesting "a walk" to everyone, the planner looks at the last 8 weeks of
recorded workouts: which activities you actually do, for how long and at what time of day.
An easy day then becomes the easy version of *your* activity, and a hard day your usual hard
session, at the time you usually train.

Activities are grouped into broad categories, and each category has one rule for its easy and
hard versions. The rules only change intensity and duration (no exercise programming), and
they are rules of thumb, not medical advice. With too little history, the planner falls back
to a generic walk or mobility session.
"""
from datetime import date, datetime, timedelta, timezone
from statistics import median

LOOKBACK_DAYS = 56
MIN_SESSIONS = 3          # an activity counts as a habit after this many sessions in the window
GENERIC = {"", "activity", "other", "unknown", "-1"}

CATEGORIES = {  # keyword -> category; first match wins, checked in this order
    "easy": ["yoga", "pilates", "walk", "stretch", "mobility", "meditation", "breathwork", "tai chi", "golf"],
    "endurance": ["run", "jog", "cycl", "bik", "spin", "swim", "row", "hik", "elliptical", "ski", "triathlon",
                  "stair", "cardio"],
    "strength": ["weight", "powerlift", "strength", "functional", "crossfit", "bodybuild", "hiit", "boot camp",
                 "calisthenics", "kettlebell"],
    "sport": ["tennis", "basketball", "soccer", "football", "badminton", "pickleball", "squash", "volleyball",
              "hockey", "rugby", "baseball", "softball", "boxing", "martial", "climb", "padel", "table tennis",
              "lacrosse", "cricket"],
}
FALLBACK_EASY = dict(title="Easy movement: walk or mobility", minutes=30, prefer=None, basis=None)
FALLBACK_HARD = dict(title="Hard session: intervals or heavy strength", minutes=60, prefer=None, basis=None)


def normalize(sport_name: str | None) -> str:
    return (sport_name or "").strip().lower().replace("_", " ").replace("-", " ")


def category(name: str) -> str:
    for cat in ("easy", "endurance", "strength", "sport"):
        if any(k in name for k in CATEGORIES[cat]):
            return cat
    return "other"


def _local_minutes(start: datetime, offset: str | None) -> int:
    from src.sources.whoop import _local, parse_offset
    t = _local(start, parse_offset(offset))
    return t.hour * 60 + t.minute


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def activity_profile(workouts: list[dict], today: date) -> dict | None:
    """The activities you do regularly, most frequent first, from workouts in the last 8 weeks.

    Each workout dict needs sport_name, start (UTC) and, if available, end, timezone_offset
    and strain. Returns None when no activity has been done often enough to count as a habit.
    """
    lo = datetime.combine(today - timedelta(days=LOOKBACK_DAYS), datetime.min.time(), timezone.utc)
    groups: dict[str, list[dict]] = {}
    for w in workouts:
        start = w.get("start")
        if start is None:
            continue
        start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        name = normalize(w.get("sport_name"))
        if name in GENERIC or start_utc < lo:
            continue
        end = w.get("end")
        minutes = None
        if end is not None:
            end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
            minutes = (end_utc - start_utc).total_seconds() / 60
        groups.setdefault(name, []).append(dict(start=_local_minutes(start, w.get("timezone_offset")),
                                                minutes=minutes, strain=w.get("strain")))
    sports = []
    for name, rows in groups.items():
        if len(rows) < MIN_SESSIONS:
            continue
        mins = [r["minutes"] for r in rows if r["minutes"] and r["minutes"] > 5]
        strains = [r["strain"] for r in rows if r["strain"] is not None]
        sports.append(dict(sport=name, category=category(name), sessions=len(rows),
                           minutes=_round5(median(mins)) if mins else None,
                           strain=round(median(strains), 1) if strains else None,
                           usual_start=int(median(r["start"] for r in rows))))
    if not sports:
        return None
    sports.sort(key=lambda s: (-s["sessions"], s["sport"]))
    return dict(sports=sports, weeks=LOOKBACK_DAYS // 7)


def _prefer(s: dict) -> tuple[int, int]:
    return (s["usual_start"] - 30, s["usual_start"] + 60)


def _basis(s: dict, weeks: int) -> str:
    return (f"Picked from your last {weeks} weeks of workouts: {s['sport']} {s['sessions']} times, "
            f"usually around {_hhmm(s['usual_start'])}.")


def easy_activity(profile: dict | None) -> dict:
    """The easy-day suggestion: an easy habit if you have one, else the easy version of your
    most frequent activity, else a walk."""
    if not profile:
        return dict(FALLBACK_EASY)
    sports = profile["sports"]
    s = next((x for x in sports if x["category"] == "easy"), None) or sports[0]
    usual = s["minutes"] or 30
    if s["category"] == "easy":
        title, minutes = f"{s['sport'].capitalize()}, as usual", min(60, max(20, usual))
    elif s["category"] == "endurance":
        title = f"Easy {s['sport']}: conversational pace"
        minutes = min(45, max(20, _round5(usual * 0.6)))
    elif s["category"] == "strength":
        title, minutes = f"Mobility or light technique work instead of heavy {s['sport']}", 30
    elif s["category"] == "sport":
        title, minutes = f"Light {s['sport']} practice, no match play (or an easy walk)", 30
    else:
        title, minutes = f"An easy, shorter {s['sport']} session", min(45, max(20, _round5(usual * 0.6)))
    return dict(title=title, minutes=minutes, prefer=_prefer(s), basis=_basis(s, profile["weeks"]))


def hard_activity(profile: dict | None) -> dict:
    """The hard-day suggestion: your most frequent activity that is not easy by nature."""
    if not profile:
        return dict(FALLBACK_HARD)
    s = next((x for x in profile["sports"] if x["category"] != "easy"), None)
    if s is None:
        return dict(FALLBACK_HARD)
    minutes = min(120, max(30, s["minutes"] or 60))
    title = {
        "endurance": f"Hard {s['sport']}: intervals or a tempo session",
        "strength": f"Heavy {s['sport']}",
        "sport": f"{s['sport'].capitalize()}: a full session or match play",
    }.get(s["category"], f"A hard {s['sport']} session")
    return dict(title=title, minutes=minutes, prefer=_prefer(s), basis=_basis(s, profile["weeks"]))
