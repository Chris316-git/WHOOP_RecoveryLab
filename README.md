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
- [ ] Experiment tracking (ABAB design, daily check-ins)
- [ ] Statistical engine (washout periods, autocorrelation, Bayesian effect estimates)
- [ ] LLM layer for experiment design and plain-language results
- [ ] Synthetic demo data with known planted effects
- [ ] Web app

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
```

`make daily-now` sends immediately; `make report-preview` builds the report into
`data/reports/` without sending it. The "Run workflow" button on GitHub also sends immediately.
The job logs never print health or calendar values, because logs of a public repo are public.
GitHub pauses scheduled workflows after 60 days without repository activity; re-enable it
from the Actions tab if that happens.

## Project layout

```
src/
  ingestion/   WHOOP OAuth, API client, payload mapping, sync, token stores
  gcal/        Google Calendar auth, sync, daily schedule features
  db/          SQLAlchemy models and session
  analysis/    Daily panel (day alignment of sleep, recovery, strain, calendar); experiment stats next
  report/      Daily summary (pure logic) and email rendering
  notify/      Email delivery
  llm/         Experiment design and explanations (in progress)
  api/         FastAPI app (login flow)
scripts/       Command-line entry points (daily.py is the scheduled job)
.github/       GitHub Actions workflow for the daily job
tests/         Unit tests for pure logic
```

## Privacy

All data stays in the database you configure. Credentials live in `.env` and `.tokens/`
(both git-ignored) or, for the scheduled job, encrypted in the database with a key that is
kept only in `.env` and GitHub Secrets. The daily email goes only to the address you set.
See [PRIVACY.md](PRIVACY.md) for exactly what is stored and how to delete it. This project is not affiliated with WHOOP and is not medical advice.

## License

MIT
