"""Run the real daily agent on the synthetic scenarios and write a report.

The agent code, tools, prompts and validator are the production ones; only the data is
synthetic (src/evals/scenarios.py) and nothing is stored or sent anywhere except the model API.
"""
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from src.agent import daily as agent
from src.coach.agent import Toolbox
from src.evals import metrics
from src.evals.scenarios import NOW, TODAY, TZ, Scenario


class EvalData:
    """The agent's tools over a scenario's synthetic data (read-only)."""

    def __init__(self, s: Scenario):
        self.s, self.tz, self.now = s, TZ, NOW

    def panel(self):
        return self.s.panel

    def workouts(self):
        return self.s.workouts

    def events(self, day):
        return (self.s.events or []) if day == TODAY else []

    def memories(self):
        return self.s.memories

    def recent_plans(self, days):
        lo = (TODAY - timedelta(days=days)).isoformat()
        return [p for p in self.s.plans if p["day"] >= lo]

    def latest_case(self):
        return TODAY.isoformat(), self.s.case

    def save_memory(self, kind, text):
        return None


def run_one(s: Scenario, model: str, api_key: str, call: Callable | None = None) -> dict:
    toolbox = Toolbox(EvalData(s), allowed=set(agent.DAILY_TOOLS))
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    record = agent.run(s.case, s.summary, toolbox, s.plans, yesterday, api_key, model, call=call)
    return metrics.score(s, record) | dict(model=model, output=record.get("output"))


def run_all(scenarios: list[Scenario], model: str, api_key: str, call_factory: Callable | None = None,
            concurrency: int = 4) -> list[dict]:
    """call_factory(scenario) -> a fake model call (tests); None uses the real API."""
    def one(s):
        return run_one(s, model, api_key, call_factory(s) if call_factory else None)
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return list(pool.map(one, scenarios))


def _fmt(v, percent: bool = True) -> str:
    if v is None:
        return "-"
    if percent and isinstance(v, float):
        return f"{100 * v:.0f}%"
    return f"{v:g}" if isinstance(v, float) else str(v)


NOT_PERCENT = {"scenarios", "errors", "tools_per_run", "input_tokens_per_run", "output_tokens_per_run",
               "latency_p50_s", "latency_p95_s"}


ROWS = [
    ("Scenarios", "scenarios"), ("Errors (API/format)", "errors"),
    ("First answer passes every check", "first_pass_rate"),
    ("Passes after at most one revision", "pass_after_revision_rate"),
    ("Falls back to the rule engine", "fallback_rate"),
    ("First answer breaks a safety expectation", "first_answer_unsafe_rate"),
    ("**Shown plan breaks a safety expectation**", "shown_unsafe_rate"),
    ("Focus matches the scenario's expectation", "focus_agreement"),
    ("Respects a constraint from memory", "memory_respected"),
    ("Unnecessary action on a normal day", "unnecessary_action_rate"),
    ("Same focus as the rule engine", "agrees_with_rules"),
    ("Tool calls per run", "tools_per_run"),
    ("Input tokens per run", "input_tokens_per_run"), ("Output tokens per run", "output_tokens_per_run"),
    ("Latency p50 (s)", "latency_p50_s"), ("Latency p95 (s)", "latency_p95_s"),
    ("Cost per run (USD)", "cost_per_run_usd"),
]


def report(results: dict[str, dict], date: str) -> str:
    """Markdown report comparing models (results: model -> aggregate)."""
    models = list(results)
    lines = [f"# Daily agent evaluation ({date})", "",
             "Synthetic scenarios run through the production agent, tools and validator "
             "(`make eval`). \"Shown\" is the plan the user would have received: the agent's if it passed "
             "every check, otherwise the rule engine's.", "",
             "| Metric | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for label, key in ROWS:
        if all(results[m].get(key) is None for m in models):
            continue
        cells = [_fmt(results[m].get(key), key not in NOT_PERCENT)
                 if key != "cost_per_run_usd" or results[m].get(key) is None
                 else f"${results[m][key]:.4f}" for m in models]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "First-answer problems by type (share of runs):", "",
              "| Type | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for c in ("grounding", "safety", "feasibility", "repeat", "format"):
        lines.append(f"| {c} | " + " | ".join(_fmt(results[m]["first_answer_problems"][c]) for m in models) + " |")
    for m in models:
        lines += ["", f"## {m}: by scenario family", "",
                  "| Family | n | First pass | Fallback | First unsafe | Shown unsafe | Focus ok | Unnecessary |",
                  "|---|---|---|---|---|---|---|---|"]
        for fam, f in results[m]["by_family"].items():
            lines.append(f"| {fam} | {f['n']} | {_fmt(f['first_pass'])} | {_fmt(f['fallback'])} | "
                         f"{_fmt(f['first_unsafe'])} | {_fmt(f['shown_unsafe'])} | {_fmt(f['focus_ok'])} | "
                         f"{_fmt(f['unnecessary'])} |")
    return "\n".join(lines) + "\n"


def dump(path, model_rows: dict[str, list[dict]], results: dict[str, dict]) -> None:
    path.write_text(json.dumps(dict(results=results, runs=model_rows), indent=1, default=str))
