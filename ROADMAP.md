# Roadmap

Recovery Lab turns wearable data and your real calendar into action. It is built around
two ideas:

- **A. Plan the day around your body and your schedule.** Each morning it judges what
  intensity of training suits today, finds real free time in Google Calendar, and proposes
  concrete blocks: training, a recovery break, a wind-down before bed. Once you confirm,
  it creates them on your calendar and adjusts them when the day changes.
- **B. Run your own habit experiments, properly.** You ask, for example, "Will skipping
  coffee after 2pm improve my sleep?" Recovery Lab helps you set up a 2-4 week plan,
  tracks whether you followed it, compares your sleep metrics, and tells you honestly
  whether the data is strong enough to support a conclusion, and what to do next.

## Market context

**A.** Wearable coaching apps already read calendars to understand a user's schedule.
Bevel, for example, reads Google and iCloud Calendar events; its official response to a user
request says the ability to write events will come "in the future"
([feedback thread](https://feedback.bevel.health/feature-requests/p/ios-calendar-google-calendar-integration),
checked October 2026). Separate user requests ask for an adaptive training calendar. That
makes **"from advice to confirmed time blocks that adapt to the day"** a concrete angle
worth exploring. The space is not empty, and competitors may ship calendar writing at
any time. What is harder to copy is the combination: recovery-aware planning, a
confirmation step, rescheduling around conflicts, and personalization from experiments.

**B.** Many apps surface correlations ("on days you did X, your sleep was Y"). The
difference here is the **whole experiment lifecycle**: a pre-registered design, guided
execution, adherence tracking, a data-quality assessment and a recommended next step.
Showing a correlation is not the goal.

Re-check competitors before making public claims.

## How A and B work together

1. **A helps B get executed.** During an experiment, the daily plan shows today's condition
   ("B day: no caffeine after 14:00") and can add a confirmed reminder to the calendar.
2. **B's results improve A.** A finished experiment ("evening training lowers your next-day
   HRV by about 5 ms") changes how A schedules things.
3. **A's choices can be experiments.** When A decides *when* to schedule something
   (training in the morning or the evening, an earlier or later wind-down), it can
   alternate in blocks. The user just follows the calendar.
4. **Passive first.** Prefer experiments whose adherence WHOOP or the calendar can verify on
   their own (bedtime, wake time, workout timing, naps, evening meetings). Experiments that
   need self-reports (caffeine, alcohol, meals) ask a single yes/no a day.

## Principles (unchanged)

- **Code computes every number; the LLM never does.** The LLM words explanations, turns
  a user's question into a structured experiment draft and describes proposed blocks. Code validates the
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

## Phase A1: Daily plan (rules only, no AI, no sport-specific library)

Goal: every morning, a short list of proposed blocks for today, each with a time slot and
a reason, in the daily email.

**1. Assess the day (deterministic):**
- **Readiness:** recovery zone, HRV and resting heart rate vs. the 30-day baseline, last night's sleep vs. need.
- **Training load:** 7-day vs 28-day strain ratio, consecutive hard days, days since the last hard session.
- **Sleep need tonight:** from WHOOP's sleep-need fields (already stored in the raw
  payloads) or the personal average, plus any sleep debt.
- **Tomorrow's constraint:** the first event tomorrow sets the latest sensible wake time.
- **Output:** a recommended intensity for today: *rest*, *recovery* (easy movement or mobility),
  *moderate* (Zone 2 or general strength) or *hard* (intervals or heavy strength), with
  target duration and heart-rate zone.

**2. Choose block types (generic, not sport-specific):**

| Block | When it is proposed |
|---|---|
| **Training** at the recommended intensity | Unless today is a rest day |
| **Recovery break** (a walk, breathing, a stretch, or a short nap window if there is sleep debt) | Red or yellow recovery, long meeting runs, or high load |
| **Wind-down** | Every day, starting about 45-60 minutes before the target bedtime (target bedtime = target wake time minus sleep need) |

**3. Find time:** use free windows from the real calendar (time blocks only). Training
needs a slot of its length plus a buffer, and hard sessions stay at least 3 hours before
the target bedtime. Respect the user's preferred hours and allowed days. If nothing fits,
offer a 15-minute version or suggest tomorrow.

**4. Explain:** each proposal carries its reasons, which code generates from the numbers
(e.g. "recovery 41%, yellow; 3 hard days in a row").

**Settings:** preferred training hours, allowed days, typical session length, wind-down
on/off and its length, and which block types to propose.

**Safety:** never push hard sessions on red days or when load is high; keep the wording
general, with a not-medical-advice note.

## Phase A2: Confirm, then write to the calendar

Goal: nothing goes on the user's calendar without their confirmation; after that, the
calendar is the reminder.

- **Confirmation (MVP, no server):** each proposal in the email carries an `.ics` file /
  "Add to calendar" link. The user's own click adds it to their calendar. No write
  permission is needed, but the app cannot move the event later.
- **Confirmation (target):** each proposal has a signed, single-use, expiring link (an HMAC
  token over user, proposal and expiry). Clicking it calls a small hosted endpoint, which
  creates the event. This is the first piece of the hosted web app (Phase D); a
  Telegram bot with buttons is an alternative.
- **Write scope:** `calendar.app.created`. The app creates a dedicated **"Recovery Lab"**
  calendar and can only touch events on it, never the user's own events. Check Google's
  current docs before building. Users re-consent once, and PRIVACY.md gets updated.
- **Events:** title (e.g. "Moderate training: Zone 2, 40 min", "Recovery walk", "Wind-down"),
  a reminder (default 15 minutes before) and the reasons in the description. Shown as busy
  by default (configurable). Excluded from our own calendar sync.
- **`planned_blocks` table:** proposal, status (proposed, confirmed, moved, done, skipped,
  expired), Google event ID, and a `user_locked` flag.
- **Adapting (confirmed events only):** every 30-minute run checks for new conflicts and
  for changed readiness, then moves, shortens or downgrades the block. It notifies the user
  and never touches an event the user moved by hand. Events are updated in place, never
  duplicated.
- **Auto-completion:** a WHOOP workout near the planned time marks training done; bedtime
  vs. target shows whether the wind-down worked.

## Phase B: Habit experiments, end to end

Goal: a user asks a question, gets a sound 2-4 week plan, is guided through it, and gets an
honest answer with a quality grade and a next step.

**1. Ask and design**
- Start from presets (caffeine cutoff, no alcohol, earlier dinner, fixed bedtime, no hard
  training after a given time). Later, the AI drafts a plan from a free-text question.
- **Pre-registration:** the primary metric (e.g. deep sleep, sleep efficiency, recovery),
  secondary metrics, the exact intervention and control, the adherence rule, the smallest
  effect worth caring about, and the analysis plan. All of it is fixed before day 1 and
  shown in the final report, so there is no picking metrics after the fact.
- **Design by type of habit:**
  - *Short-acting* (caffeine, alcohol, dinner time, screens): randomized days or short
    blocks of 3-4 days within 2-4 weeks. Many switches protect against trends.
  - *Slower-acting* (bedtime regularity, training patterns): ABAB with 7-day phases.
  - Washout nights after switches where carryover is plausible.
  - The current engine allows 7-14 day phases; extend it to randomized-day and short-block
    designs.
- **Feasibility check before starting:** using the user's own day-to-day variability and
  autocorrelation, simulate how big an effect this length could detect (e.g. "with 4 weeks
  you could detect about ±12 min of deep sleep"). If that is unrealistic, suggest a longer
  plan or a less noisy metric.

**2. Execute and track**
- The daily email (and an optional confirmed calendar reminder from A) shows today's condition.
- One-tap yes/no check-in; adherence from WHOOP or the calendar where possible.
- Automatic flags: travel or time zone change, illness signals (skin temperature,
  respiratory rate), packed days, missing nights.
- Mid-experiment nudges when adherence drops or too many nights are missing.

**3. Analyze (deterministic engine)**
- Bayesian regression with AR(1) errors, controlling for strain, calendar load and day of week.
- Intention-to-treat and per-protocol results; the effect size with a credible interval;
  the probability of a benefit and of a meaningful benefit.
- Calibrate the engine before release (90% intervals must cover ~90% in simulation) and
  validate it on synthetic data with planted effects.

**4. Quality assessment ("report card")**
- Adherence rate per condition; usable days per condition; missing and flagged nights.
- **Balance check:** were strain, calendar load and weekends similar across conditions?
- Washout and carryover handled? ITT and per-protocol consistent?
- **Grade:** *conclusive*, *suggestive* or *insufficient*, with the specific reasons.

**5. Follow-up**
- Recommend one of: **adopt** the habit, **extend** (code calculates roughly how many more
  days are needed), **repeat** to confirm, **refine** (change the dose or timing), or **drop**.
- Save the result, with its grade, to the personal pattern archive. Conclusive findings can
  change how A plans the day.

**Data:** the `experiments`, `experiment_days` and `daily_checkins` tables from the WIP
branch, plus a pre-registration snapshot, an assessment record and follow-up decisions.

## Phase C: AI layer (serves A and B)

- `src/llm/` with the Anthropic SDK; prompts stored as versioned files; structured (JSON
  schema) output.
- **Guardrails:** a numeric consistency check (every number in the output must appear in the
  input), exercises only from the library, and a template fallback when the API fails. The
  email is always sent.
- Uses, in order:
  1. A short plain-language opening for the daily email.
  2. Turning a proposed block into a friendly, specific description (what to do, why today).
  3. Explaining experiment results (ITT vs per-protocol, how sure we are).
  4. Turning a user's question ("does coffee after 2pm hurt my sleep?") into a structured
     experiment draft that code validates and the user confirms.
- Use a small, fast model for daily text and a stronger one for design. Send only
  aggregates, never raw records or calendar data. Unit tests use a mocked client; a golden
  set of synthetic cases checks direction and overclaiming.

## Phase D: Hosted multi-user version

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

- **Pattern discovery (observational screening):** scan passive factors (bedtime regularity,
  workout timing, meeting load, travel, weather, illness signals) for associations, label
  them as unverified, and offer them as experiment ideas for B. Same model and controls,
  with shrinkage / multiple-comparison control. Not a priority: B's value is the lifecycle,
  not finding correlations.
- **Sport-specific blocks:** goal templates and a reviewed exercise library (e.g. golf:
  rotational power, hip and thoracic mobility, anti-rotation, single-leg stability), with
  concrete exercises, equipment guidance and benchmark tests. Parked until the generic daily
  plan works; the AI layer would then pick exercises from the library only.
- **Nutrition guidance:** parked. If revisited, start with training-linked fueling tips; any
  calorie targets would need safety floors, would be opt-in, would exclude minors and would
  point at-risk users to professionals. Nutrient values would come from a nutrition
  database (e.g. USDA FoodData Central), never from the LLM.
- More sport templates (running, basketball, tennis, swimming, general fitness).
- Weekly planning: plan the next week on Sunday, adjust daily.
- Training block reviews: completion, benchmark changes, recovery trends, what's next.
- Other wearables (Oura, Garmin, Apple Health) behind a common ingestion interface.
- Use upcoming free time (e.g. "Thursday 14:00-16:00 is open") in proactive suggestions.

## Order of work

1. **A1:** readiness and intensity rules, block selection and slot finding (pure functions
   with tests), then a "Today's plan" section in the daily email.
2. **B, core:** merge and calibrate the WIP engine; presets; pre-registration;
   randomized-day and short-block designs; feasibility check; daily condition in the
   email; check-ins; quality report card; follow-up recommendation.
3. **A2:** confirm-then-create (`.ics` first, then signed links and the dedicated calendar).
4. **C:** AI layer, then **D:** hosted version.

Work starts on the author's go-ahead.
