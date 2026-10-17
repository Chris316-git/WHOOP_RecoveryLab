"""The daily pipeline as separate, injectable stages.

    due?  ->  sync sources  ->  build report (+ check yesterday)  ->  ready?  ->  record  ->  deliver

Every dependency (database sessions, settings, token store, mail sender, clock) is passed
in, so the stages can be reused from a script, a web endpoint, a notebook or a test, and
each one can be run on its own. Nothing here prints health or calendar values: stage
results carry statuses only, because the scheduled job's logs are public.
"""
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.db.models import DailyPlan, Experiment, User, UserSettings
from src.db.upsert import upsert
from src.feedback.outcome import evaluate
from src.planner.focus import TITLES
from src.planner.habits import activity_profile, parse_sports
from src.report.daily import build_daily_summary
from src.report.data import (
    load_events_for_day,
    load_experiments,
    load_not_useful,
    load_plan,
    load_recent_focuses,
    load_recent_panel,
    load_recent_plans,
    load_recent_workouts,
)
from src.report.render import render_email
from src.report.schedule import (
    ReportSchedule,
    in_window,
    ready_to_send,
    resolve_timezone,
)
from src.settings import Settings

Sender = Callable[[str, str, str, str], None]   # (to, subject, html, text)
Clock = Callable[[ZoneInfo], datetime]
REVIEW_DAYS = 3   # re-check outcomes this many days back while their data was missing


def _system_clock(zone: ZoneInfo) -> datetime:
    return datetime.now(zone)


def short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160] if str(exc) else ''}"


@dataclass
class UserRun:
    """What happened for one user. Statuses only, safe to log."""
    user_id: str
    outcome: str = "pending"        # skipped | waiting | sent | previewed | failed
    detail: str = ""
    notices: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    trace: str = ""                 # full traceback on failure; print locally only (may contain data)

    @property
    def ok(self) -> bool:
        return self.outcome in ("skipped", "waiting") or (self.outcome in ("sent", "previewed") and not self.notices)


@dataclass
class DailyPipeline:
    session_factory: Callable
    settings: Settings
    whoop_store: object                              # FileTokenStore or DbTokenStore
    google_users: set[str] = field(default_factory=set)
    sender: Sender | None = None                     # defaults to SMTP from settings
    clock: Clock = _system_clock
    preview_dir: Path | None = None
    wording_call: Callable | None = None             # LLM transport; None = the Claude API (tests inject a fake)
    reasoning_call: Callable | None = None           # same, for the AI reasoning engine

    # ---- stage 0: context ----
    def context(self, user_id: str) -> tuple[str, ReportSchedule]:
        with self.session_factory() as session:
            user = session.get(User, int(user_id))
            row = session.get(UserSettings, int(user_id))
            tz = resolve_timezone(row.timezone if row else None, user.timezone if user else None,
                                  self.settings.report_timezone)
            return tz, ReportSchedule.from_row(row)

    # ---- stage 1: sync ----
    def sync_sources(self, user_id: str, run: UserRun) -> None:
        from src.gcal.sync import sync_calendar
        from src.ingestion.sync import sync_user
        from src.ingestion.whoop_client import WhoopClient
        try:
            with self.session_factory() as session:
                sync_user(WhoopClient(user_id, self.whoop_store), session)
            run.steps.append("whoop synced")
        except Exception as exc:  # keep going: an older report is better than none
            run.notices.append("WHOOP sync failed; showing the latest stored data. If this repeats, "
                               "re-authorize WHOOP locally (make server, /login).")
            run.steps.append(f"whoop sync failed ({short_error(exc)})")
        if user_id in self.google_users:
            try:
                with self.session_factory() as session:
                    sync_calendar(int(user_id), session)
                run.steps.append("calendar synced")
            except Exception as exc:
                run.notices.append("Google Calendar sync failed (authorization may have expired). "
                                   "Run make connect-google locally.")
                run.steps.append(f"calendar sync failed ({short_error(exc)})")

    # ---- stage 2: build ----
    def build_summary(self, user_id: str, tz: str, now: datetime) -> dict:
        today, uid = now.date(), int(user_id)
        with self.session_factory() as session:
            panel = load_recent_panel(session, uid, today)
            events = load_events_for_day(session, uid, today, tz) if user_id in self.google_users else None
            recent = load_recent_focuses(session, uid, today)
            muted = load_not_useful(session, uid, today)
            prefs = session.get(UserSettings, uid)
            habits = activity_profile(load_recent_workouts(session, uid, today), today,
                                      preferred_sports=parse_sports(prefs.sports if prefs else None))
            plans = {k: load_plan(session, uid, today - timedelta(days=k)) for k in range(1, REVIEW_DAYS + 1)}
            history = load_recent_plans(session, uid, today)
            experiments, answers = load_experiments(session, uid)
        summary = build_daily_summary(panel, today, tz, events, now=now, recent_focuses=recent, not_useful=muted,
                                      habits=habits)
        # Did the recent focuses happen? Read from the wearable data, so nobody has to check in.
        # Yesterday's is shown in the email; older days are re-checked while their data was
        # still missing (e.g. sleep not scored yet when the email went out).
        summary["reviews"] = {}
        for k, plan in plans.items():
            if plan is None or (k > 1 and plan["outcome"] not in (None, "no_data")):
                continue
            plan["title"] = plan.get("title") or TITLES.get(plan["focus"], plan["focus"])
            review = evaluate(plan, panel, today - timedelta(days=k))
            if review:
                summary["reviews"][k] = review
        summary["yesterday"] = summary["reviews"].get(1)
        self.experiment_context(summary, experiments, answers, panel, today)
        from src.reasoning.evidence import build_case
        summary["reasoning_case"] = build_case(summary, panel, today, now, habits, history)
        return summary

    def experiment_context(self, summary: dict, experiments: list[dict], answers: dict, panel, today) -> None:
        """Active experiment, a finished one awaiting keep/extend/drop, today's proposal, or the
        presets the AI may propose (all decided in code)."""
        from src.experiments.daily import decision_card, eligible_presets, experiment_today
        from src.experiments.presets import preset
        from src.planner.focus import usual_bedtime
        summary["kept_habits"] = [dict(title=preset(e["preset"])["title"],
                                       verdict=e["result"]["primary"]["itt"]["verdict"])
                                  for e in experiments if e.get("next_step") == "keep" and e.get("result")]
        active = next((e for e in experiments if e["status"] == "active"), None)
        if active:
            info = experiment_today(active, answers, panel, today, usual_bedtime(panel, today))
            summary["experiment"] = info
            block = summary["focus"].get("block")
            words = preset(active["preset"])["conflict_words"]
            if info.get("arm") == "control" and block and any(w in block["title"].lower() for w in words):
                block["title"] = "Wind down: lights low, slow down"   # never contradict tonight's assignment
            return
        card = next((c for c in (decision_card(e, today) for e in experiments) if c), None)
        if card:
            summary["experiment"] = card
        proposed = next((e for e in experiments if e["status"] == "proposed"
                         and e.get("proposed_on") == today.isoformat()), None)
        if proposed:
            spec = preset(proposed["preset"])
            summary["experiment_proposal"] = dict(id=proposed["id"], preset=proposed["preset"], title=spec["title"],
                                                  question=spec["question"], nights=proposed["nights"],
                                                  why=proposed.get("reason"))
        elif not card:
            history = int(panel["recovery_score"].notna().sum()) if "recovery_score" in panel else 0
            summary["experiment_options"] = [dict(preset=k, title=preset(k)["title"], question=preset(k)["question"],
                                                  nights=preset(k)["nights"])
                                             for k in eligible_presets(experiments, today, history)]

    # ---- stage 2a: AI reasoning ----
    def reason(self, summary: dict, run: UserRun) -> None:
        """Let the AI decide today's focus from the evidence. Its plan replaces the rule engine's
        only if it passes every check (and REASONING_MODE is "ai"); both are stored for evaluation."""
        from src.reasoning.engine import reason
        summary["reasoning"] = dict(status="off", problems=[], output=None)
        mode, case = self.settings.reasoning_mode, summary.get("reasoning_case")
        has_key = bool(self.settings.anthropic_api_key) or self.reasoning_call is not None
        if mode == "off" or case is None or not has_key or not summary.get("last_night_scored"):
            return
        result = reason(case, summary, self.settings.anthropic_api_key or "test", self.settings.reasoning_model,
                        call=self.reasoning_call)
        summary["reasoning"] = {k: result[k] for k in ("status", "problems", "output")}
        detail = f" ({', '.join(result['problems'])})" if result["problems"] else ""
        run.steps.append(f"reasoning: {result['status']}{detail}")   # labels only, never content
        if result["status"] == "ok" and mode == "ai":
            summary["rule_focus"] = summary["focus"]
            summary["focus"] = result["focus"]
            if result.get("proposal") and summary.get("experiment_options"):
                summary["experiment_proposal"] = dict(result["proposal"], new=True)

    def explain_experiment(self, summary: dict, run: UserRun) -> None:
        """Plain-language explanation of a just-finished experiment by the LLM (numbers checked)."""
        info = summary.get("experiment") or {}
        if not info.get("done") or info.get("decide") or not (self.settings.anthropic_api_key or self.wording_call):
            return
        from src.experiments.explain_ai import explain_result
        from src.experiments.presets import preset
        message, status = explain_result(info["result"], preset(info["preset"]),
                                         self.settings.anthropic_api_key or "test", self.settings.llm_model,
                                         call=self.wording_call)
        if message:
            info["explanation"] = info["result"]["ai_explanation"] = message
        run.steps.append(f"experiment explanation: {status}")

    # ---- stage 2b: wording ----
    def word(self, summary: dict, run: UserRun) -> None:
        """Friendlier wording of the focus by the LLM, with numeric checks and a template fallback.
        Only the status is logged, never the text."""
        from src.llm.wording import word_focus
        if not self.settings.anthropic_api_key and self.wording_call is None:
            return
        if summary["focus"].get("engine") == "ai":   # the AI already wrote its own headline
            return
        message, status = word_focus(summary, self.settings.anthropic_api_key or "test", self.settings.llm_model,
                                     call=self.wording_call)
        if message:
            summary["focus"]["message"] = message
        run.steps.append(f"wording: {status}")

    # ---- stage 3: deliver ----
    def deliver(self, summary: dict, notices: list[str]) -> None:
        subject, html, text = render_email(summary, notices)
        send = self.sender
        if send is None:
            from src.notify.emailer import send_email
            send = lambda to, s, h, t: send_email(to, s, h, t, self.settings.smtp)  # noqa: E731
        send(self.settings.require("report_email_to"), subject, html, text)

    def save_preview(self, user_id: str, summary: dict, notices: list[str]) -> Path:
        _, html, text = render_email(summary, notices)
        directory = self.preview_dir or Path("data/reports")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{summary['date']}-{user_id}.html"
        path.write_text(html)
        path.with_suffix(".txt").write_text(text)
        return path

    # ---- stage 4: record ----
    def save_plan(self, user_id: str, summary: dict, now: datetime, tz: str) -> str:
        """Store today's focus before sending (the email's links point at it). A plan the user
        already decided on is left alone. Returns the plan's status."""
        f = summary["focus"]
        with self.session_factory() as session:
            existing = session.get(DailyPlan, (int(user_id), now.date()))
            if existing is not None and (existing.response or existing.calendar_status):
                summary["decided"] = dict(response=existing.response, calendar_status=existing.calendar_status,
                                          block=existing.final_block)
                return "decided"
            rule = summary.get("rule_focus") or f
            r = summary.get("reasoning") or {}
            upsert(session, DailyPlan, [dict(
                user_id=int(user_id), day=now.date(), focus=f["focus"], score=float(f["score"] or 0.0),
                title=f.get("title"), engine=f.get("engine", "rules"),
                reasons=f["reasons"], block=f["block"], considered=[list(c) for c in f["considered"]],
                timezone=tz,
                rule_focus=dict(focus=rule["focus"], title=rule.get("title"), score=rule.get("score"),
                                confidence=rule.get("confidence"), block=rule.get("block")),
                ai_output=r.get("output"), ai_status=r.get("status"), ai_problems=r.get("problems") or None,
                evidence=summary.get("reasoning_case"),
            )], ["user_id", "day"])
            session.commit()
        return "open"

    def save_outcome(self, user_id: str, summary: dict, now: datetime) -> None:
        """Store what the wearable says about recent focuses on their plans."""
        reviews = summary.get("reviews") or {}
        if not reviews:
            return
        with self.session_factory() as session:
            for k, review in reviews.items():
                p = session.get(DailyPlan, (int(user_id), now.date() - timedelta(days=k)))
                if p is None:
                    continue
                p.outcome = review["outcome"]
                p.outcome_detail = dict(review["detail"], recovery_before=review["recovery_before"],
                                        recovery_after=review["recovery_after"])
                p.outcome_checked_at = datetime.now(timezone.utc)
            session.commit()

    def warm_up(self) -> None:
        """Wake the free-tier web host just before the email goes out, so the first click on a
        button does not wait for a cold start. Best effort: failures are ignored."""
        if not self.settings.actions_enabled:
            return
        try:
            import httpx
            httpx.get(f"{self.settings.public_base_url}/healthz", timeout=60)
        except Exception:
            pass

    def save_experiment_result(self, user_id: str, summary: dict) -> None:
        """Store the analysis once, when an experiment has finished."""
        info = summary.get("experiment") or {}
        if not info.get("done"):
            return
        with self.session_factory() as session:
            e = session.get(Experiment, info["id"])
            if e is not None and e.status == "active":
                e.status, e.result, e.ended_at = "completed", info["result"], datetime.now(timezone.utc)
                session.commit()

    def save_proposal(self, user_id: str, summary: dict, now: datetime) -> None:
        """Store a new AI proposal as a 'proposed' experiment, waiting for Start / Not now."""
        import secrets

        from src.experiments.presets import preset
        p = summary.get("experiment_proposal")
        if not p or not p.get("new"):
            return
        with self.session_factory() as session:
            e = Experiment(user_id=int(user_id), preset=p["preset"], start_day=now.date(),
                           nights=preset(p["preset"])["nights"], seed=secrets.randbelow(2**31), schedule=[],
                           status="proposed", proposed_on=now.date(), reason=p["why"], extensions=0)
            session.add(e)
            session.commit()
            p["id"] = e.id

    def experiment_links(self, user_id: str, summary: dict, now: datetime) -> dict:
        """Signed one-tap links for the experiment card (valid ~2 days): last night's Yes / No,
        keep / extend / drop after a result, stop, Start / Not now for a proposal, and browse."""
        from datetime import date as _date
        from datetime import time

        from src.actions.tokens import ActionToken, sign
        if not self.settings.actions_enabled:
            return {}
        expires = int(datetime.combine(now.date() + timedelta(days=2), time(6), now.tzinfo).timestamp())
        base, key = self.settings.public_base_url, self.settings.action_signing_key

        def link(action: str, day) -> str:
            return f"{base}/a/{sign(ActionToken(int(user_id), day, action, expires), key)}"

        links, x, p = {}, summary.get("experiment") or {}, summary.get("experiment_proposal")
        if x.get("ask"):
            day = _date.fromisoformat(x["ask"]["day"])
            links.update(adhere_yes=link("adhere_yes", day), adhere_no=link("adhere_no", day))
        if x:
            start = _date.fromisoformat(x["start_day"])
            if x.get("done"):
                for step in x["result"].get("steps") or ["keep", "drop"]:
                    links[f"exp_{step}"] = link(f"exp_{step}", start)
            else:
                links["exp_stop"] = link("exp_stop", start)
        if p:
            links.update(exp_start=link("exp_start", now.date()), exp_decline=link("exp_decline", now.date()))
        if not x.get("arm") and not p:
            links["exp_browse"] = link("exp_browse", now.date())
        return links

    def action_links(self, user_id: str, summary: dict, now: datetime) -> dict | None:
        """Signed links, valid until 06:00 the next morning. Add to calendar / Change time /
        Dismiss only when a time block actually helps; otherwise just a quiet "Not useful?"."""
        focus = summary["focus"]
        if not self.settings.actions_enabled or focus.get("focus") in (None, "none"):
            return None
        actions = ("add", "change", "dismiss") if focus.get("schedulable") else ("not_useful",)
        from datetime import time

        from src.actions.tokens import ActionToken, sign
        expires = int(datetime.combine(now.date() + timedelta(days=1), time(6), now.tzinfo).timestamp())
        base, key = self.settings.public_base_url, self.settings.action_signing_key
        return {a: f"{base}/a/{sign(ActionToken(int(user_id), now.date(), a, expires), key)}"
                for a in actions}

    def mark_sent(self, user_id: str, now: datetime) -> None:
        with self.session_factory() as session:
            upsert(session, UserSettings, [dict(user_id=int(user_id), last_report_on=now.date())], ["user_id"])
            session.commit()

    # ---- the whole flow for one user ----
    def run_user(self, user_id: str, mode: str = "scheduled") -> UserRun:
        """mode: "scheduled" (respect the user's schedule), "now" or "preview"."""
        run = UserRun(user_id)
        tz, schedule = self.context(user_id)
        zone = ZoneInfo(tz)
        if mode == "scheduled":
            due, reason = in_window(schedule, self.clock(zone))
            if not due:
                run.outcome, run.detail = "skipped", reason
                return run
        self.sync_sources(user_id, run)
        now = self.clock(zone)
        summary = self.build_summary(user_id, tz, now)
        if mode == "scheduled":
            ready, reason = ready_to_send(schedule, now, summary["last_night_scored"])
            if not ready:
                run.outcome, run.detail = "waiting", reason
                return run
            run.detail = reason
        self.reason(summary, run)
        self.explain_experiment(summary, run)
        self.word(summary, run)
        if mode == "preview":
            path = self.save_preview(user_id, summary, run.notices)
            run.outcome, run.detail = "previewed", str(path)
            return run
        status = self.save_plan(user_id, summary, now, tz)
        self.save_outcome(user_id, summary, now)
        self.save_experiment_result(user_id, summary)
        self.save_proposal(user_id, summary, now)
        summary["experiment_links"] = self.experiment_links(user_id, summary, now)
        if summary["experiment_links"] and not summary.get("actions"):
            self.warm_up()
        if status == "open":
            summary["actions"] = self.action_links(user_id, summary, now)
            if summary["actions"]:
                self.warm_up()
        self.deliver(summary, run.notices)
        if mode == "scheduled":  # a manual send (make daily-now) is a test; it never cancels the real one
            self.mark_sent(user_id, now)
        run.outcome = "sent"
        return run

    def run_all(self, mode: str = "scheduled") -> list[UserRun]:
        runs = []
        for user_id in self.whoop_store.list_users():
            try:
                runs.append(self.run_user(user_id, mode))
            except Exception as exc:
                runs.append(UserRun(user_id, outcome="failed", detail=short_error(exc),
                                    trace=traceback.format_exc()))
        return runs
