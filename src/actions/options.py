"""Alternative time slots for "Change time". Pure logic, no I/O."""
from src.planner.focus import _to_hhmm, _to_min

MAX_OPTIONS = 4


def slot_options(block: dict, free_windows: list[dict], focus: str) -> list[dict]:
    """Other slots for the same block today.

    Daytime blocks: the same duration at the start of each other free window (and later in a
    long window), plus a shorter version. Wind-down blocks: 30 minutes earlier or later.
    """
    minutes = int(block["minutes"])
    title = block["title"]
    current = _to_min(block["start"])
    out: list[dict] = []

    def add(start: int, length: int, label: str):
        if any(o["start"] == _to_hhmm(start) and o["minutes"] == length for o in out) or len(out) >= MAX_OPTIONS:
            return
        if start == current and length == minutes:
            return
        out.append(dict(start=_to_hhmm(start), end=_to_hhmm(start + length), minutes=length, title=title,
                        label=label))

    if focus == "prioritize_sleep":
        add(current - 30, minutes, "30 minutes earlier")
        add(current + 30, minutes, "30 minutes later")
        return out

    for w in free_windows:
        s, e = _to_min(w["start"]), _to_min(w["end"])
        if e - s >= minutes:
            add(s, minutes, f"{minutes} min")
            if e - s >= minutes + 120:
                add(e - minutes, minutes, f"{minutes} min, later in that gap")
    short = max(10, minutes // 2)
    for w in free_windows:
        s, e = _to_min(w["start"]), _to_min(w["end"])
        if e - s >= short and short < minutes:
            add(s, short, f"Shorter version, {short} min")
            break
    return out
