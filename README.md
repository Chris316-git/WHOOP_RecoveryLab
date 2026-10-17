# Recovery Lab

**Find out what actually works for your body, using your own data.**

Wearables tell you how you slept. Chatbots can guess why. Recovery Lab runs
structured **N-of-1 experiments** on your wearable data to estimate the *causal*
effect of a habit change (e.g. "no caffeine after 2pm") on sleep and recovery,
and schedules its recommendations around the time you actually have free.

## What makes it different

| | Wearable app | Chatbot + exported data | Recovery Lab |
|---|---|---|---|
| Describes your metrics | Yes | Yes | Yes |
| Separates cause from coincidence | No | No | **ABAB experiments + statistical modeling** |
| Numbers computed by | Vendor | LLM (can hallucinate) | **Deterministic stats engine; LLM only explains** |
| Knows your schedule | No | No | **Calendar-aware recommendations** |
| Builds long-term knowledge | No | Per chat | **Persistent log of verified personal patterns** |

## Architecture

```
WHOOP API ─OAuth─┐
                 ├─> Ingestion ─> Postgres ─> Stats engine ─> LLM layer ─> App
Google Calendar ─┘    (daily sync)  (per-user)   (experiments)   (explain / propose)
```

- **Multi-user by design:** every table is keyed by `user_id`; credentials are stored per user.
- **Privacy first:** calendar sync stores only time blocks (start, end, busy/free, attendee count).
  Event titles, descriptions, locations and attendee identities are never stored.
- **Full raw payloads** from WHOOP are kept in JSONB so new fields can be used without re-fetching.

## Status

- [x] WHOOP OAuth 2.0 with automatic token refresh
- [x] Full-history backfill and incremental sync (cycles, recovery, sleep, workouts)
- [x] Google Calendar sync with daily schedule features
- [x] Daily morning email: sync, compare last night with your 30-day baseline, list today's free blocks
- [x] Scheduled cloud job (GitHub Actions) with OAuth tokens encrypted in the database
- [x] Per-user send time and time zone
- [x] Personal trends: HRV and resting heart rate vs. your normal range, sleep shortfall, training load, weekday patterns
- [x] Daily planner: one focus a day (or "nothing to change"), placed in real free time between 07:00 and midnight
- [x] Suggestions built from your own workout history: the easy or hard version of the activities you actually do, at your usual time
- [x] Optional one-tap "Add to calendar" (with Undo) for focuses that need a time block, on a dedicated "Recovery Lab" calendar
- [x] AI reasoning engine (optional): Claude decides the focus and designs the action from a numbered evidence file, a code validator checks every claim, the rule engine is the fallback, and both are stored for evaluation
- [x] Yesterday's focus checked from wearable data (no check-ins), stored apart from what was scheduled
- [ ] Feedback loop, the rest: did it help, over many days?
- [x] Personal experiment engine v0.1: one preset, randomized paired nights, one-tap adherence, randomization test
- [x] Experiments from the email: AI-suggested (checked), browse page, AI explanation of results, keep / extend / drop
- [ ] Adaptive personalization: structured AI memory computed in code
- [ ] Hosted multi-user web app

See [ROADMAP.md](ROADMAP.md) for the plan and the design behind each step.

## Quick start

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), a WHOOP membership,
a Postgres database (Supabase works out of the box), and a Google Cloud project.

```bash
git clone https://github.com/<your-username>/recovery-lab.git
cd recovery-lab
make setup
cp .env.example .env          # then fill in the values
make init-db
make server                   # open http://localhost:8000/login and authorize WHOOP
make sync-whoop               # in a second terminal
make connect-google           # one-time browser authorization
make sync-calendar
```

## Daily report (automated)

Every morning a GitHub Actions job syncs WHOOP and Google Calendar, builds a short report
and emails it to you: last night's recovery, HRV, resting heart rate and sleep compared with
your own 30-day baseline, the 7-day trend, today's busy hours and free blocks, and a few
rule-based hints. All numbers are computed by code; the hints are labeled as heuristics,
not causal findings.

One-time setup:

1. `make gen-key` and put the output in `.env` as `TOKEN_ENCRYPTION_KEY`.
2. `make init-db` (creates the `oauth_tokens` table), then `make migrate-tokens`, then set
   `TOKEN_STORE=db` in `.env`. Local runs and the cloud job now share one encrypted store,
   which matters because WHOOP rotates refresh tokens on every refresh.
3. Create a Gmail app password (Google Account -> Security -> 2-Step Verification -> App passwords).
4. In the GitHub repo: Settings -> Secrets and variables -> Actions, add `DATABASE_URL`,
   `TOKEN_ENCRYPTION_KEY`, `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `SMTP_USER`,
   `SMTP_PASSWORD`, `REPORT_EMAIL_TO`.
5. Actions tab -> "Daily sync and report" -> Run workflow, to test it once.

**Choosing when it arrives.** The job checks every 30 minutes and sends at most one report
per day, in your own time zone: not before your chosen time and, by default, only after
WHOOP has scored last night's sleep (with a deadline, so a late score never means no email).

```bash
make settings                          # show current settings (default: after 10:00, by 13:00)
make settings ARGS="--time 10:30"      # earliest send time
make settings ARGS="--latest 12:00"    # send by then even if sleep is not scored yet
make settings ARGS="--no-wait"         # send at --time without waiting for the score
make settings ARGS="--off"             # pause (use --on to resume)
make settings ARGS="--tz Asia/Shanghai"  # pick a time zone; "--tz auto" follows Google Calendar
make settings ARGS="--sports golf,running"  # activities to suggest; "auto" learns them from your workouts
```

`make daily-now` sends immediately; `make report-preview` builds the report into
`data/reports/` without sending it. The "Run workflow" button on GitHub also sends immediately.
The job logs never print health or calendar values, because logs of a public repo are public.
GitHub pauses scheduled workflows after 60 days without repository activity; re-enable it
from the Actions tab if that happens.

## Add to calendar (optional)

The email is meant to be read in 15 seconds and then closed; ignoring it is a fine response.
Only when today's focus comes with a time block (an easy walk, a wind-down before bed, a break
in a busy day, a hard session) does it carry two buttons: **Add to calendar** puts the block on a
calendar the app creates for you ("Recovery Lab", with a 15-minute reminder) in one tap, and
**Change time** offers other free slots today. A quiet **Dismiss** link sits next to them, with
no questions asked. Every result page has **Undo**. When there is no block (no free time fits,
or nothing needs to change), there are no buttons.

Three things are stored separately in `daily_plans`, because they mean different things:
whether you responded (no response is *not* a rejection), whether something is on the
calendar, and what actually happened. The last one is read from your wearable the next
morning (strain for "take it easy" or "hard session", bedtime for "protect your sleep") and
shown as one line in the email, so there is nothing to check in. A focus you mark "not
useful" needs stronger evidence to come back for two weeks.

The buttons need a small public endpoint (the FastAPI app):

1. `make connect-google` once more, to grant the narrow `calendar.app.created` permission
   (it only covers calendars the app creates).
2. `make gen-key` and save the output as `ACTION_SIGNING_KEY` (a different value from
   `TOKEN_ENCRYPTION_KEY`).
3. Deploy: on Render, New > Blueprint > this repository (`render.yaml`). Fill in
   `DATABASE_URL`, `TOKEN_ENCRYPTION_KEY` and `ACTION_SIGNING_KEY`.
4. Add the service URL as `PUBLIC_BASE_URL`, and `ACTION_SIGNING_KEY`, to `.env` and to the
   GitHub Actions secrets.

Links are signed and expire at 06:00 the next morning. Mail scanners open links in emails on
their own, so opening a link never changes anything by itself: the page sends the action with
a line of JavaScript (which most scanners do not run) and shows a plain button otherwise.
Without `PUBLIC_BASE_URL`, emails are sent without buttons.

## AI reasoning engine (optional)

With `ANTHROPIC_API_KEY` set, the morning plan is decided by a Claude model instead of the rule
engine, within limits enforced in code:

1. **Evidence builder** (`src/reasoning/evidence.py`): numbered facts computed in Python
   (today's state, trends vs. your normal range, load, sleep, free time, your activities, and
   the last 7 days of suggestions, responses and measured outcomes).
2. **Reasoning** (`src/reasoning/engine.py`): the model decides what matters most today and
   designs one action, e.g. a smaller step when earlier advice kept not being followed.
   It returns structured JSON with cited evidence ids, uncertainty and hedged hypotheses.
3. **Safety validator** (`src/reasoning/validate.py`): cited ids must exist, every number must
   come from the evidence, no hard session against the data, calendar blocks only in free
   time and early enough before bedtime, no medical, medication or diet advice. Any failure
   falls back to the rule engine.
4. **Evaluation** (`src/reasoning/evaluate.py`, `uv run python scripts/evaluate.py`): pass
   rate and rejection reasons, blocked unsafe suggestions, agreement with the rules, use of
   personal context, and responses and outcomes by engine.

`REASONING_MODE=shadow` keeps showing the rules' plan while still recording the AI's, and
`REASONING_MODE=off` disables it. The calendar is still only written when you tap the button.

## Personal experiments (v0.1)

WHOOP can show that a habit and your recovery move together. An experiment asks whether the
habit actually changes things *for you*:

Everything happens from the email:

* **Suggested by the AI**: when nothing is running and your data makes one relevant, the email
  shows a suggestion (at most one a week; a declined one stays quiet for a month) with
  **Start experiment** / **Not now**. The AI picks from presets and must cite your evidence; it
  cannot invent interventions or outcomes.
* **Or pick one yourself**: "Browse experiments" in the email footer opens a page with all presets.
* **At the end**: the verdict, a plain-language explanation (written by the AI from the computed
  numbers, checked like everything else, with a template fallback) and a next step decided in
  code: **Keep it**, **Extend** (once, by 6 nights) or **Drop it**. Kept habits become evidence
  for future plans.

Presets: no screens 30 minutes before bed (outcome: sleep performance), no hard training after
20:00 (HRV), no caffeine after 14:00 (sleep performance). A command line exists for testing:
`uv run python scripts/experiment.py list | start <preset> | status | stop`.

* **Design** (`src/experiments/design.py`): nights in pairs, a seeded coin decides which night of
  each pair is the treatment night. Tonight's assignment appears in the morning email.
* **Adherence** is your one-tap Yes/No the next morning. Wearable data is shown only as a hint,
  never as proof, and never doubles as the outcome.
* **Analysis** (`src/experiments/analysis.py`): mean pair difference in the pre-specified outcome
  (sleep performance for the first preset), a randomization test and a 95% t-interval, as
  assigned (primary) and per protocol. Verdicts are pre-specified: helped, worse, no
  meaningful effect, inconclusive, or not enough data. A simulation test checks the method on
  autocorrelated synthetic nights: about 5% false positives and about 95% interval coverage.
* While an experiment runs, neither the rule engine nor the AI may contradict tonight's
  assignment.

## Project layout

```
src/
  ingestion/   WHOOP OAuth, API client, payload mapping, sync, token stores
  gcal/        Google Calendar auth, sync, daily schedule features
  sources/     Wearable adapters: vendor rows -> device-agnostic DailyRecords (whoop.py)
  analysis/    DailyRecord contract and the daily panel (day alignment of sleep, readiness, load, calendar)
  report/      Trend signals, daily summary and email rendering (pure logic)
  planner/     Today's focus: scoring, threshold, time slot, activity habits (pure logic)
  feedback/    Did yesterday's focus happen? Checked from wearable data (pure logic)
  pipeline/    The daily pipeline as injectable stages: sync -> build -> record -> deliver
  db/          SQLAlchemy models, session factories, upsert, encrypted credentials
  notify/      Email delivery
  settings.py  Runtime settings as one immutable object (from .env / environment)
  actions/     Add to calendar / Change time / Dismiss / Undo: signed links, calendar writes, pages
  experiments/ Personal experiments: presets, randomized schedule, analysis, the email card
  reasoning/   AI reasoning engine: evidence builder, LLM call, safety validator, evaluation report
  llm/         Claude API helper and the wording fallback for rule-based plans
  api/         FastAPI app: WHOOP login flow and the action endpoint
scripts/       Thin command-line entry points (daily.py runs the pipeline)
.github/       GitHub Actions workflow for the daily job
tests/         Unit tests for the pure logic, plus an end-to-end pipeline test on in-memory SQLite
```

### Design for reuse

- **Device-agnostic core.** Adapters in `src/sources/` turn vendor data into `DailyRecord`s
  (`src/analysis/records.py`). The panel, signals, planner and report only see records, so
  adding Oura or Garmin means writing one adapter.
- **Pure functions in the middle.** `build_panel`, `compute_signals`, `choose_focus` and
  `render_email` take data and return data. They do no I/O, so they are unit-tested and can be
  called from a notebook or another service.
- **Dependencies are injected.** `DailyPipeline` receives its session factory, `Settings`, token
  store, mail sender and clock. The end-to-end test runs it against in-memory SQLite with a
  fake sender and a fixed clock:

```python
from src.db.session import make_session_factory
from src.pipeline.daily import DailyPipeline
from src.settings import Settings

settings = Settings.from_env()
pipeline = DailyPipeline(session_factory=make_session_factory(settings.database_url),
                         settings=settings, whoop_store=my_store, sender=my_sender)
runs = pipeline.run_all(mode="preview")   # or run_user(user_id, mode="now")
```

## Privacy

All data stays in the database you configure. Credentials live in `.env` and `.tokens/`
(both git-ignored) or, for the scheduled job, encrypted in the database with a key that is
kept only in `.env` and GitHub Secrets. The daily email goes only to the address you set.
See [PRIVACY.md](PRIVACY.md) for exactly what is stored and how to delete it. This project is not affiliated with WHOOP and is not medical advice.

## License

MIT
