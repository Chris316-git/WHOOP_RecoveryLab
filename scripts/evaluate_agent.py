"""Evaluate the daily agent offline on synthetic scenarios, and compare models.

    make eval                                                  # default model, 8 scenarios per family
    make eval ARGS="--models claude-sonnet-5-5,claude-haiku-5-5"
    make eval ARGS="--per-family 3 --families sleep_debt,prompt_injection"
    make eval ARGS="--price claude-sonnet-5-5=3,15"            # USD per million input,output tokens

Writes evals/REPORT.md (latest comparison) and evals/results/<timestamp>.json (every run).
Needs ANTHROPIC_API_KEY. Only synthetic data is sent; nothing is stored in the database.
Prices change: copy them from the Anthropic pricing page to get a cost estimate.
"""
import argparse
import sys
from datetime import datetime

import _bootstrap  # noqa: F401

from src import config
from src.evals import metrics, runner
from src.evals.scenarios import build_scenarios
from src.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", help="comma-separated; default REASONING_MODEL")
    parser.add_argument("--per-family", type=int, default=8)
    parser.add_argument("--families", help="comma-separated subset")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--price", action="append", default=[], help="model=input,output (USD per 1M tokens)")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.anthropic_api_key:
        sys.exit("Set ANTHROPIC_API_KEY in .env first.")
    models = [m.strip() for m in (args.models or settings.reasoning_model).split(",") if m.strip()]
    prices = {}
    for p in args.price:
        name, _, pair = p.partition("=")
        i, _, o = pair.partition(",")
        prices[name.strip()] = (float(i), float(o))
    scenarios = build_scenarios(args.per_family, families=args.families.split(",") if args.families else None)

    results, rows = {}, {}
    for m in models:
        print(f"{m}: {len(scenarios)} scenarios...")
        rows[m] = runner.run_all(scenarios, m, settings.anthropic_api_key, concurrency=args.concurrency)
        results[m] = metrics.aggregate(rows[m], prices.get(m))
        r = results[m]
        print(f"  first pass {r['first_pass_rate']}, fallback {r['fallback_rate']}, "
              f"shown unsafe {r['shown_unsafe_rate']}, p50 {r['latency_p50_s']}s")

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    out = config.PROJECT_ROOT / "evals"
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "REPORT.md").write_text(runner.report(results, stamp[:10]))
    runner.dump(out / "results" / f"{stamp}.json", rows, results)
    print("Wrote evals/REPORT.md and evals/results/" + stamp + ".json")
    if any(r["shown_unsafe_rate"] for r in results.values()):
        sys.exit("A shown plan broke a safety expectation: see the report.")


if __name__ == "__main__":
    main()
