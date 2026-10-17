"""What kind of activity to suggest, learned from the user's own workout history. Pure logic.

Instead of suggesting "a walk" to everyone, the planner looks at the last 8 weeks of
recorded workouts: which activities you actually do, for how long and at what time of day.
An easy day then becomes the easy version of *your* activity, and a hard day your usual hard
session, at the time you usually train.

The activities you list with `make settings ARGS="--sports golf,running"` come first. The
time is always learned: a session is placed near when you usually do that activity, morning
or afternoon.

Walking is treated with care: wearables often record it automatically (a walk home, an
evening stroll), so it is neither taken as "your sport" nor used to infer a training time.
A walk goes into free time in the afternoon, and never late in the evening. It is also the
fallback when nothing else is known.

Activities are grouped into broad categories, and each category has one rule for its easy and
hard versions. The rules only change intensity and duration (no exercise programming), and
they are rules of thumb, not medical advice.
"""
from datetime import date, datetime, timedelta, timezone
from statistics import median

LOOKBACK_DAYS = 56
MIN_SESSIONS = 2          # an activity counts as a habit after this many sessions in the window
GENERIC = {"", "activity", "other", "unknown", "-1"}

CATEGORIES = {  # keyword -> category; checked in this order, first match wins
    "easy": ["yoga", "pilates", "walk", "stretch", "mobility", "meditation", "breathwork", "tai chi"],
    "endurance": ["run", "jog", "cycl", "bik", "spin", "swim", "row", "hik", "elliptical", "ski", "triathlon",
                  "stair", "cardio"],
    "strength": ["weight", "powerlift", "strength", "functional", "crossfit", "bodybuild", "hiit", "boot camp",
                 "calisthenics", "kettlebell"],
    "sport": ["golf", "tennis", "basketball", "soccer", "football", "badminton", "pickleball", "squash", "volleyball",
              "hockey", "rugby", "baseball", "softball", "boxing", "martial", "climb", "padel", "lacrosse", "cricket"],
}
# Activities whose easy / hard versions read better with their own wording.
SPECIFIC = {
    "golf": dict(easy=("Golf: range or short-game practice", 45), hard=("Golf: a full round", 240)),
}
DEFAULT_MINUTES = {"easy": 30, "endurance": 45, "strength": 60, "sport": 60, "other": 45}
WALK_LATEST_END = 20 * 60   # walks end by 20:00
FALLBACK_EASY = dict(title="Easy movement: walk or mobility", minutes=30, prefer=None, basis=None,
                     latest_end=WALK_LATEST_END)
FALLBACK_HARD = dict(title="Hard session: intervals or heavy strength", minutes=60, prefer=None, basis=None,
                     latest_end=None)


def normalize(sport_name: str | None) -> str:
    return (sport_name or "").strip().lower().replace("_", " ").replace("-", " ")


def category(name: str) -> str:
    for cat in ("easy", "endurance", "strength", "sport"):
        if any(k in name for k in CATEGORIES[cat]):
            return cat
    return "other"


def is_walking(name: str) -> bool:
    return "walk" in name


def _specific(name: str) -> dict | None:
    return next((v for k, v in SPECIFIC.items() if k in name), None)


def _local_minutes(start: datetime, offset: str | None) -> int:
    from src.sources.whoop import _local, parse_offset
    t = _local(start, parse_offset(offset))
    return t.hour * 60 + t.minute


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def parse_sports(text: str | None) -> list[str]:
    return [normalize(s) for s in (text or "").split(",") if normalize(s)]


def activity_profile(workouts: list[dict], today: date, preferred_sports: list[str] | None = None) -> dict | None:
    """Your activities, most relevant first: the ones you chose (`preferred_sports`), then the
    ones recorded at least MIN_SESSIONS times in the last 8 weeks, most frequent first.

    Each workout dict needs sport_name, start (UTC) and, if available, end, timezone_offset and
    strain. Returns None when nothing is known.
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

    def entry(name: str, rows: list[dict], chosen: bool) -> dict:
        mins = [r["minutes"] for r in rows if r["minutes"] and r["minutes"] > 5]
        strains = [r["strain"] for r in rows if r["strain"] is not None]
        return dict(sport=name, category=category(name), sessions=len(rows), chosen=chosen,
                    minutes=_round5(median(mins)) if mins else None,
                    strain=round(median(strains), 1) if strains else None,
                    usual_start=int(median(r["start"] for r in rows)) if rows else None)

    chosen = preferred_sports or []
    sports = [entry(name, groups.get(name, []), True) for name in chosen]
    others = [entry(name, rows, False) for name, rows in groups.items()
              if name not in chosen and len(rows) >= MIN_SESSIONS]
    sports += sorted(others, key=lambda s: (-s["sessions"], s["sport"]))
    if not sports:
        return None
    return dict(sports=sports, weeks=LOOKBACK_DAYS // 7)


def _prefer(s: dict) -> tuple[int, int] | None:
    """Around when you usually do this activity. None (the planner's afternoon default) for
    walks, which are often recorded automatically, and for activities with no history yet."""
    t = None if is_walking(s["sport"]) else s["usual_start"]
    return None if t is None else (t - 30, t + 60)


def _basis(s: dict, profile: dict) -> str:
    usual = (f", usually around {_hhmm(s['usual_start'])}"
             if s["usual_start"] is not None and not is_walking(s["sport"]) else "")
    if s["chosen"]:
        recorded = f" ({s['sessions']} times in the last {profile['weeks']} weeks{usual})" if s["sessions"] else ""
        return f"You listed {s['sport']} as an activity you do{recorded}."
    return f"Picked from your last {profile['weeks']} weeks of workouts: {s['sport']} {s['sessions']} times{usual}."


def easy_activity(profile: dict | None) -> dict:
    """The easy-day suggestion, in this order: an activity you listed; an easy habit such as
    yoga (not walking); the easy version of your main activity; a walk."""
    if not profile:
        return dict(FALLBACK_EASY)
    sports = profile["sports"]
    s = (next((x for x in sports if x["chosen"]), None)
         or next((x for x in sports if x["category"] == "easy" and not is_walking(x["sport"])), None)
         or next((x for x in sports if not is_walking(x["sport"])), None)
         or sports[0])
    usual = s["minutes"] or DEFAULT_MINUTES[s["category"]]
    special = _specific(s["sport"])
    if special:
        title, minutes = special["easy"]
    elif s["category"] == "easy":
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
    return dict(title=title, minutes=minutes, prefer=_prefer(s), basis=_basis(s, profile),
                latest_end=WALK_LATEST_END if is_walking(s["sport"]) else None)


def hard_activity(profile: dict | None) -> dict:
    """The hard-day suggestion: the first activity (listed by you, else most frequent) that is
    not easy by nature."""
    if not profile:
        return dict(FALLBACK_HARD)
    s = next((x for x in profile["sports"] if x["category"] != "easy"), None)
    if s is None:
        return dict(FALLBACK_HARD)
    special = _specific(s["sport"])
    usual = s["minutes"] or DEFAULT_MINUTES[s["category"]]
    if special:
        title, default = special["hard"]
        minutes = min(300, max(60, s["minutes"])) if s["minutes"] else default
    else:
        minutes = min(120, max(30, usual))
        title = {
            "endurance": f"Hard {s['sport']}: intervals or a tempo session",
            "strength": f"Heavy {s['sport']}",
            "sport": f"{s['sport'].capitalize()}: a full session or match play",
        }.get(s["category"], f"A hard {s['sport']} session")
    return dict(title=title, minutes=minutes, prefer=_prefer(s), basis=_basis(s, profile), latest_end=None)
