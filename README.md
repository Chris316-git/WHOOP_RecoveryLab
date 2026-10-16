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

## Project layout

```
src/
  ingestion/   WHOOP OAuth, API client, payload mapping, sync
  gcal/        Google Calendar auth, sync, daily schedule features
  db/          SQLAlchemy models and session
  analysis/    Experiment statistics (in progress)
  llm/         Experiment design and explanations (in progress)
  api/         FastAPI app (login flow)
scripts/       Command-line entry points
tests/         Unit tests for pure logic
```

## Privacy

All data stays in the database you configure. Credentials live in `.env` and `.tokens/`,
both git-ignored. This project is not affiliated with WHOOP and is not medical advice.

## License

MIT
