"""Write the public demo page from one run of the real pipeline on today's data.

    make demo              # sync, run the daily agent and one coach question (no email, nothing saved)
    make demo ARGS=--no-sync
    make demo ARGS='--question "I want to fall asleep earlier"'

Then open docs/index.html, check it, and commit it; GitHub Pages serves it from docs/.
The page shows your real numbers for one day. Calendar events appear only as busy/free time,
buttons are inert, and the HTML is scanned for email addresses, action links and other
private values before it is written. Nothing is stored in the database.
"""
import argparse
import sys
from zoneinfo import ZoneInfo

import _bootstrap  # noqa: F401

from src import config
from src.db.schema import ensure_schema
from src.db.session import make_session_factory
from src.demo.page import build_page, privacy_problems, stress_test
from src.demo.snapshot import example_card, experiment_progress
from src.experiments.simulation import calibration, power
from src.gcal.google_auth import connected_users
from src.ingestion.token_store import get_whoop_store
from src.pipeline.daily import DailyPipeline, UserRun
from src.report.data import load_experiments, load_recent_panel
from src.report.render import render_email
from src.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-sync", action="store_true", help="use the data already in the database")
    parser.add_argument("--question", default="I want to fall asleep earlier. What should I change this week?",
                        help="what to ask the coach")
    parser.add_argument("--no-coach", action="store_true", help="leave out the coach exchange")
    args = parser.parse_args()

    settings = Settings.from_env()
    factory = make_session_factory(settings.require("database_url"))
    ensure_schema(factory.kw["bind"])
    store = get_whoop_store()
    users = store.list_users()
    if not users:
        sys.exit("No connected WHOOP account.")
    uid = users[0]
    pipeline = DailyPipeline(session_factory=factory, settings=settings, whoop_store=store,
                             google_users=set(connected_users()))

    run = UserRun(uid)
    tz, _ = pipeline.context(uid)
    if not args.no_sync:
        pipeline.sync_sources(uid, run)
    now = pipeline.clock(ZoneInfo(tz))
    summary = pipeline.build_summary(uid, tz, now)
    rule_focus = summary["focus"]
    pipeline.reason(summary, run)
    pipeline.explain_experiment(summary, run)
    pipeline.word(summary, run)
    # inert buttons: same layout as the real email, no signed links
    summary["experiment_links"] = {k: "#" for k in pipeline.experiment_links(uid, summary, now)}
    summary["actions"] = {k: "#" for k in pipeline.action_links(uid, summary, now) or {}}
    _, email_html, _ = render_email(summary, run.notices)

    case = summary.get("reasoning_case") or {"evidence": []}
    reasoning = summary.get("reasoning") or {}
    with factory() as session:
        panel = load_recent_panel(session, int(uid), now.date())
        experiments, answers = load_experiments(session, int(uid))

    coach = None
    if not args.no_coach and settings.anthropic_api_key:
        print("Asking the coach...")
        from src.coach.agent import COACH_TOOLS, Toolbox, chat
        from src.coach.tools import CoachData
        allowed = {t["name"] for t in COACH_TOOLS} - {"remember"}     # the demo never writes memory
        toolbox = Toolbox(CoachData(factory, int(uid), tz, now), allowed=allowed)
        result = chat([dict(role="user", content=args.question)], toolbox, settings.anthropic_api_key,
                      settings.reasoning_model)
        coach = dict(question=args.question, reply=result["reply"], tools_used=result["tools_used"],
                     proposals=result["proposals"], checked=result["checked"], sources=result.get("sources") or [])

    print("Scoring knowledge retrieval...")
    from src.evals.retrieval import QUERIES, evaluate
    from src.knowledge.retrieval import get_index
    index = get_index(settings)
    labels = dict(bm25="Keyword (BM25)", dense=f"Dense ({settings.voyage_model})", hybrid="Hybrid (RRF)")
    modes = ["bm25"] + (["dense", "hybrid"] if index.dense_ready else [])
    if index.dense_ready:
        index.prime([q for q, _ in QUERIES])
    retrieval = [dict(evaluate(index, m), label=labels[m]) for m in modes]
    from src.demo.page import parse_report
    report = config.PROJECT_ROOT / "evals" / "REPORT.md"
    agent_eval = parse_report(report.read_text()) if report.exists() else None

    print("Running the simulation checks...")
    snapshot = dict(
        date=now.date().isoformat(), weekday=now.strftime("%A"), time=now.strftime("%H:%M"), timezone=tz,
        email_html=email_html, case=case, reasoning=reasoning, rule_focus=rule_focus,
        model=settings.reasoning_model,
        stress=stress_test(reasoning.get("output"), case, dict(summary, focus=rule_focus)),
        agent=summary.get("agent"), coach=coach, retrieval=retrieval, chunks=len(index.chunks),
        agent_eval=agent_eval,
        experiment=experiment_progress(experiments, answers, panel, now.date()),
        calibration=calibration(), power=power(), example_card=example_card(),
    )
    html = build_page(snapshot)

    problems = privacy_problems(html, [settings.report_email_to, settings.action_signing_key,
                                       settings.anthropic_api_key, str(uid) if len(str(uid)) >= 5 else ""])
    if problems:
        sys.exit("Not written: the page would contain " + ", ".join(problems) + ".")
    out = config.PROJECT_ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    (out / ".nojekyll").write_text("")
    print(f"Wrote docs/index.html [{'; '.join(run.steps)}]. Open it, check it, then commit docs/.")


if __name__ == "__main__":
    main()
