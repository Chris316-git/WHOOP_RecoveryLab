# Roadmap

Recovery Lab is a personal coach that runs on your own data. Every day it tells you what to
do, puts it into the free time on your calendar, and quietly learns what works for *your*
body.

## Product shape: two layers

| Layer | What the user sees | Why it matters |
|---|---|---|
| **Front: daily guidance and reminders** (core) | What to train today, the exact exercises, scheduled into a free slot of the calendar with a reminder | Useful every day. Needs no expertise and no logging |
| **Back: experiments and pattern discovery** | An occasional "want to try this?" and later "here is what we found about you" | Makes the guidance personal over time, and is the reason to trust it |

How the layers connect:

1. **Recommendations double as experiments.** When the app decides *when* to schedule
   training (morning or evening, say), it can alternate in an ABAB pattern. The user just
   follows the calendar; WHOOP records what happened.
2. **Findings feed back into recommendations.** "Evening training lowers your next-day HRV by
   about 5 ms" turns into "schedule training before 18:00 when possible".
3. **Passive first.** Prefer experiments whose adherence WHOOP or the calendar can verify on
   their own (bedtime, wake time, workout timing, naps, evening meetings). Experiments that
   need self-reports (caffeine, alcohol, meals) are optional and ask a single yes/no a day.

## Principles (unchanged)

- **Code computes every number; the LLM never does.** The LLM picks exercises from a
  reviewed library, words explanations and proposes experiment designs. Code validates the
  structured output and checks that every number in the text appears in the input data.
- **Correlation is labeled as correlation.** Only completed experiments produce causal claims.
- **Privacy first.** Minimal data, encrypted credentials, calendar time blocks only, no
  health values in logs.
- **Multi-user by design**, used first by the author.

## Done

- WHOOP OAuth, token refresh, full backfill and incremental sync
- Google Calendar sync (time blocks only) and daily schedule features
- Daily email: last night vs. your 30-day baseline, 7-day trend, today's free blocks, rule-based hints
- GitHub Actions job every 30 minutes; per-user send time, time zone and "wait for sleep score"
- OAuth tokens encrypted in the database; privacy policy
- Work in progress (not merged): experiment tables, ABAB design, Bayesian AR(1) engine,
  synthetic data generator. The interval calibration still needs work: 90% credible
  intervals currently cover about 80-88% in simulation.

## Phase 1: Training recommendations (rules only, no AI)

Goal: the daily email says what to train today, with concrete exercises.

- **Training profile:** goal sport and block length (e.g. golf, 6 weeks), level, days per
  week, session length, available equipment, injuries to avoid.
- **Exercise library:** `data/exercises/<sport>.json`, reviewed and kept in git. Each exercise
  has the quality it trains, equipment, steps, sets/reps, cues, common mistakes,
  regression/progression, a no-equipment alternative, difficulty, contraindications and a
  demo link (links only, no re-hosted videos). Start with **golf** (about 25-30 exercises).
  Have a certified coach or physical therapist review it before others use it.
- **Sport templates:** the qualities to build, weekly structure, block phases (base → build →
  deload/retest), benchmark tests, simple fueling and recovery tips (no calorie targets).
  Golf: rotational power, hip and thoracic mobility, core anti-rotation, single-leg
  stability, lower-body strength, walking endurance.
- **Daily adjustment rules:**
  - *Recovery zone:* green = as planned; yellow = reduced intensity; red = mobility or rest.
  - *Training load:* 7-day vs 28-day strain ratio; deload when it is high.
  - *Variety:* avoid repeating the same category or muscle group on consecutive days.
  - *Time:* fit the free blocks; if there is no time, give a 15-minute version.
  - *Sleep:* keep hard sessions at least 3 hours before the usual bedtime.
- **Equipment guidance:** filter by what the user has, plus a "buy one thing first" list
  (bands → medicine ball → foam roller → dumbbells). Generic types only, no brands; any
  affiliate links would be disclosed.
- **Safety:** cap weekly progression, exclude exercises that conflict with reported
  injuries, separate beginner and experienced paths, show a not-medical-advice note.

## Phase 2: Write sessions to the calendar

Goal: users get reminded by their calendar, not by having to read the email.

- Use the narrow `calendar.app.created` scope: the app creates a dedicated **"Recovery Lab"**
  calendar and can only touch events on it. Check Google's current documentation before
  starting.
- Event: title, start/end time in a free slot, a reminder (default 15 minutes before), and
  the exercise list, demo links and "why today" in the description.
- Shown as *busy* by default to protect the time (configurable). Excluded from our own
  calendar sync so it never counts as schedule load.
- New table `planned_sessions`: the plan, the Google event ID, the status (planned, moved,
  done, skipped) and a `user_locked` flag.
- Every 30-minute run: if a new meeting conflicts, move the session to the next free slot
  (or shorten it, or move it to tomorrow) and notify. If recovery drops, swap in a lighter
  session. Never move an event the user moved by hand. Update events in place, never
  duplicate them.
- Auto-completion: a WHOOP workout near the planned time marks the session done; otherwise
  the next email asks.
- Settings: on/off, earliest and latest training time, allowed days, reminder minutes,
  busy/free.
- Non-Google users: attach an `.ics` file to the email.
- Update PRIVACY.md to say the app writes events to its own calendar. Users re-consent once.

## Phase 3: AI layer

- `src/llm/` with the Anthropic SDK; prompts stored as versioned files; structured (JSON
  schema) output.
- **Guardrails:** a numeric consistency check (every number in the output must appear in the
  input), exercises only from the library, and a template fallback when the API fails. The
  email is always sent.
- Uses, in order:
  1. A short plain-language opening for the daily email.
  2. Turning the selected exercises into a coherent session, with "why today".
  3. Explaining experiment results (ITT vs per-protocol, how sure we are).
  4. Proposing experiment designs from a user's goal or suspicion.
- Use a small, fast model for daily text and a stronger one for design. Send only
  aggregates, never raw records or calendar data. Unit tests use a mocked client; a golden
  set of synthetic cases checks direction and overclaiming.

## Phase 4: Experiments and pattern discovery

- Finish the WIP engine: calibrate the intervals, keep ITT and per-protocol results, and
  validate on synthetic data with planted effects.
- **Pattern discovery (observational):** use the same model and controls (strain, calendar
  load, day of week, autocorrelation) on naturally occurring variation in passive factors:
  - bedtime and its regularity, sleep debt, naps;
  - workout timing, type and intensity;
  - meeting load, evening meetings, early first meetings;
  - travel and time zone changes;
  - weather (temperature, humidity; no reporting needed);
  - illness signals (skin temperature, respiratory rate, SpO2).

  Apply shrinkage / multiple-comparison control, and present the results as "correlation,
  not yet verified" with an offer to test.
- **Experiment suggestions:** from clues, from common factors (caffeine, alcohol, late meals,
  irregular sleep, late hard training), from a one-time habits questionnaire, and from the
  user's own suspicion. Rank by expected effect × ease × uncertainty, and accept with one tap.
- **Embedded experiments:** let the scheduler alternate session timing (or similar) in ABAB
  blocks, with adherence verified by WHOOP.
- **Personal pattern archive:** completed experiments become entries that change
  recommendations and inform the next suggestions.
- Not planned: inferring unreported behaviors (e.g. guessing that someone drank alcohol from
  their physiology). It is inaccurate and intrusive.
- Not planned: experiments on sport results such as golf scores. They are too noisy and too
  infrequent. Use benchmark tests (mobility, balance, throw distance) to track a training
  block instead, and report change without causal claims.

## Phase 5: Hosted multi-user version

- Deploy the FastAPI app (e.g. Render, Fly.io or Railway) with web OAuth for WHOOP and
  Google; a settings page (send time, time zone, training profile, calendar options).
- Store each user's email address in the database; send through a transactional email
  service instead of Gmail.
- Low-friction input: one-click yes/no links in the email or a Telegram bot.
- Account controls: disconnect, export, delete all data.
- Google OAuth verification for sensitive scopes (up to 100 test users before that); check
  WHOOP's developer terms for third-party apps; host a homepage and the privacy policy on
  our own domain.
- Move to Alembic once schema changes become frequent.

## Later / parked

- **Nutrition guidance:** parked. If revisited, start with training-linked fueling tips; any
  calorie targets would need safety floors, would be opt-in, would exclude minors and would
  point at-risk users to professionals. Nutrient values would come from a nutrition
  database (e.g. USDA FoodData Central), never from the LLM.
- More sport templates (running, basketball, tennis, swimming, general fitness).
- Weekly planning: plan the next week on Sunday, adjust daily.
- Training block reviews: completion, benchmark changes, recovery trends, what's next.
- Other wearables (Oura, Garmin, Apple Health) behind a common ingestion interface.
- Use upcoming free time (e.g. "Thursday 14:00-16:00 is open") in proactive suggestions.

## Next step

Phase 1, starting with the golf exercise library and the training profile.
