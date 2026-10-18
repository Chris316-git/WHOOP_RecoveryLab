"""Pieces of the demo snapshot that are pure logic (the database work is in scripts/demo.py)."""
import random
from datetime import date

from src.experiments.analysis import analyze, explain
from src.experiments.daily import nights_with_outcomes, recommended_step
from src.experiments.presets import preset
from src.experiments.simulation import simulate_nights
from src.report.render import _experiment


def experiment_progress(experiments: list[dict], answers: dict, panel, today: date) -> dict | None:
    """The active experiment up to today. Later nights are left out: their assignment stays hidden."""
    active = next((e for e in experiments if e["status"] == "active"), None)
    if active is None or not active.get("schedule"):
        return None
    spec = preset(active["preset"])
    column = spec["outcome"]["column"]
    nights = [dict(day=n["day"], arm=n["arm"], adherence=n.get("adherence"), outcome=n.get(column))
              for n in nights_with_outcomes(active, answers, panel) if date.fromisoformat(n["day"]) <= today]
    if not nights:
        return None
    return dict(title=spec["title"], question=spec["question"], night=len(nights), total=active["nights"],
                outcome_label=spec["outcome"]["label"], nights=nights)


def example_card(seed: int = 11, effect: float = 5.0, preset_key: str = "screens_off_30") -> str:
    """A finished, simulated experiment as the email would show it (inert buttons)."""
    spec = preset(preset_key)
    rng = random.Random(seed)
    nights = simulate_nights(effect, rng, pairs=spec["nights"] // 2, base=80.0)
    column = spec["outcome"]["column"]
    for i, n in enumerate(nights):
        n[column] = round(n.pop("y"))
        n[spec["secondary"]["column"]] = None
        # one missed habit night, to show the per-protocol idea
        n["adherence"] = ("no" if i == 4 else "yes") if n["arm"] == "treatment" else None
    result = analyze(nights, spec)
    step, steps = recommended_step(result["primary"]["itt"]["verdict"], 0)
    result.update(recommended=step, steps=steps)
    info = dict(title=spec["title"], done=True, result=result, explanation=explain(result, spec))
    links = {f"exp_{s}": "#" for s in steps}
    return _experiment(dict(experiment=info, experiment_links=links))
