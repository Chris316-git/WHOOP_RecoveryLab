# Roadmap

Recovery Lab is a personal health decision system. It turns wearable data and your real
calendar into one clear decision a day, and then checks whether that decision helped. It is
not a dashboard of more numbers, and it is not "WHOOP data pasted into a chatbot". It is
built to answer three questions:

1. **What should I do today?** One focus, placed in real free time, or "nothing needs to change".
2. **Why should I do it?** Reasons computed from your own data, compared with your own baseline.
3. **Did it actually help?** Feedback every day, and proper experiments when you want certainty.

> Working name: Recovery Lab. A rename is under consideration (e.g. "PulsePilot"). Before
> renaming, check that the name is free (other products, trademarks, domains, GitHub), and
> drop "WHOOP" from the repository name so the product does not use a third-party brand.

## Market context

**Planning around the calendar.** Wearable coaching apps already read calendars. Bevel, for
example, reads Google and iCloud Calendar events; its official response to a user request
says the ability to write events will come "in the future"
([feedback thread](https://feedback.bevel.health/feature-requests/p/ios-calendar-google-calendar-integration),
checked October 2026). Other user requests there ask for an adaptive training calendar.
**"From advice to a confirmed time block that adapts to the day"** is a concrete angle
worth exploring, but the space is not empty, and competitors may ship calendar writing at
any time. What is harder to copy is the combination: one well-chosen focus, a confirmation
step, a feedback loop, and personalization grounded in experiments.

**Experiments.** Many apps surface correlations. The difference here is the whole
lifecycle: a pre-registered design, a length set by the user's own data, guided execution,
a data-quality assessment, and a recommended next step, which may well be "not enough data
yet".

Re-check competitors before making public claims.

## Principles

- **One focus a day, and silence is a valid output.** The planner picks the single most
  useful change for today. When nothing stands out, it says so. Knowing when *not* to give
  advice is part of being smart.
- **Code computes every number; the LLM never does.** Python and SQL compute baselines,
  scores, intervals and memory facts. The LLM chooses wording, explains, and drafts
  experiment plans. Code validates structured output, and every number in generated text
  must appear in the input.
- **The user stays in control.** Nothing lands on the calendar without confirmation, and
  every proposal can be accepted, adjusted or declined.
- **Correlation is labeled as correlation.** Only completed experiments produce causal claims.
- **Privacy first.** Minimal data, encrypted credentials, calendar time blocks only, no
  health values in logs, and only aggregates sent to the LLM.
- **No more feature expansion for now.** Daily planner + feedback + experiments + memory
  is the scope. Everything else waits in "Later".

## Done

- WHOOP OAuth, token refresh, full backfill and incremental sync
- Google Calendar sync (time blocks only) and daily schedule features
- Daily email: last night vs. your 30-day baseline, 7-day trend, today's free blocks, rule-based hints
- GitHub Actions job every 30 minutes; per-user send time, time zone and "wait for sleep score"
- Personal trends in the email: HRV and resting heart rate vs. your normal range, 7-night sleep
  shortfall, training load ratio and hard-day streaks, weekday sleep patterns
- OAuth tokens encrypted in the database; privacy policy
- Work in progress (not merged): experiment tables, ABAB design, Bayesian AR(1) engine,
  synthetic data generator. The intervals still need calibration: 90% credible intervals
  currently cover about 80-88% in simulation.

## Phase 1: Daily health intelligence (done)

Goal: each morning, an accurate picture of where you stand relative to *your own* normal.

- Last night vs. the 30-day baseline (median and percentile), and today's calendar load.
- **Trends** (`src/report/signals.py`):
  - HRV (log scale) and resting heart rate: the last 7 days vs. a normal range (mean ± 0.5 SD,
    with a minimum width) from the 30 days before them.
  - Sleep shortfall over the last 7 nights vs. WHOOP's baseline sleep need (8 h assumed, and
    labeled as such, when unavailable).
- **Training load:** the 7-day vs. 28-day mean strain ratio, and consecutive hard days (strain ≥ 14).
- **Weekday pattern:** mentioned only when tonight's weekday is reliably a short-sleep night
  (≥ 30 min less, on at least 75% of those nights over the last 8 weeks).
- Every signal needs a minimum amount of history; otherwise it is left out instead of guessed.
  These signals are the inputs for Phase 2.

## Phase 2: Daily planner, with one focus a day

Goal: one recommendation a day that fits your body and your calendar, which you can accept,
adjust or decline.

**Status:** steps 1, 2 and the "Today's focus" email card are done (`src/planner/focus.py`,
plans saved to `daily_plans`). Next: step 3 (accept / adjust / decline), then step 4.

**1. Choose today's focus (deterministic).** Code builds candidate focuses and scores each one
by *how far today deviates from your baseline × whether you can act on it today*:

| Candidate focus | Typical trigger |
|---|---|
| Go hard today (strength or intervals) | Good readiness, low recent load, the goal calls for it |
| Lower the intensity | High recent load, or HRV trending down |
| Prioritize sleep tonight | Sleep debt, or a short night |
| Recover between commitments | A long run of meetings with low readiness |
| Nothing needs to change | No candidate clears the threshold |

- **No nagging:** sleep shortfall is judged against *your* usual week (a chronically short
  sleeper is not told "sleep more" every day), an assumed 8 h need counts for less, and a
  focus already chosen on each of the last two days needs stronger evidence to be repeated.
  On synthetic data this gives a focus on about a quarter of days and "nothing needs to
  change" on the rest.
- Only the top candidate is sent, and only if it clears a threshold. Otherwise the email says
  "all normal, keep your plan". The planner proposes at most one calendar block a day.
- **Intensity uses several signals,** not the recovery score alone: HRV and resting heart rate
  trends, the load ratio, last night's sleep, the user's goal, and an optional one-tap
  "how fresh do you feel?" (1-5). It must work without the self-report.
- Every focus carries its reasons, generated from the numbers (e.g. "HRV below your 30-day
  range for 3 days; yesterday's strain 16.2").

**2. Find time.** Use free windows from the real calendar. Hard sessions stay at least
3 hours before the target bedtime. Respect the user's preferred hours and allowed days. If
nothing fits, offer a shorter version or suggest tomorrow. "Prioritize sleep" becomes a
wind-down block that starts 45-60 minutes before the target bedtime (target wake time minus
sleep need).

**3. Accept / adjust / decline.**
- The email carries **signed, single-use, expiring links** (an HMAC token over user,
  proposal, action and expiry). A small hosted endpoint receives the click. "Adjust" opens a
  minimal page to change the time or duration. This endpoint is the first piece of the
  hosted version; a full dashboard comes much later.
- On accept, the event is created in a dedicated **"Recovery Lab"** calendar using the
  narrow `calendar.app.created` scope (the app can only touch events on its own calendar).
  Check Google's current documentation first; users re-consent once; update PRIVACY.md.
- Fallback with no server: an `.ics` "add to calendar" attachment (the user's click adds it;
  the app cannot move it later).
- After confirmation, the block is moved or shortened if a new meeting conflicts or
  readiness drops. Blocks the user moved by hand are never touched, and events are updated
  in place, never duplicated.

**4. Wording.** The LLM turns the computed focus, reasons and slot into a short, friendly
message (e.g. "Good morning: your recovery is below your recent level and yesterday was a
hard day, so today should be light. You are free at 17:30. Shall I add a 30-minute easy
session?"). Guardrails: the numeric consistency check, structured input only, and a
template fallback when the API fails, so the email always goes out.

**Data:** `daily_plans` (the date, the chosen focus, its score and reasons, the proposed
block and its status) and the Google event ID.

## Phase 3: Feedback loop

Goal: know, every day, whether recommendations are followed and whether they help.

- **Log every decision:** accepted, adjusted (and how), declined, or ignored.
- **Did it happen?** Training is checked against WHOOP workouts near the planned time; a
  wind-down is checked against the actual bedtime vs. the target.
- **Did it help?** A one-tap "was today's advice helpful?" in the next morning's email.
  Asked only on days with a confirmed recommendation, to avoid notification fatigue.
- **Outcome tracking:** next-day readiness after followed vs. not-followed recommendations.
  This is reported descriptively, as an association; Phase 4 provides the causal evidence.
- The same one-tap mechanism later serves experiment check-ins.

**Data:** `recommendation_feedback` (plan, action, adjustment, helpful, completion source).

## Phase 4: Personal experiment engine

Goal: a user asks something like "Will skipping coffee after 2pm improve my sleep?" and gets a
sound plan, guided execution and an honest answer.

**1. Ask and design**
- Start from presets (caffeine cutoff, no alcohol, earlier dinner, fixed bedtime, no hard
  training after a set time). Later, the LLM drafts a plan from a free-text question, and
  code validates it.
- **Pre-registration,** fixed before day 1 and shown in the final report: the primary and
  secondary metrics, intervention and control, the adherence rule, the smallest effect worth
  caring about, the analysis plan and the **stopping rule**. This rules out picking metrics
  afterwards and stopping as soon as the results look good.
- **Design by type of habit:**
  - *Short-acting* (caffeine, alcohol, dinner time, screens): randomized days or 3-4 day blocks.
  - *Slower-acting* (bedtime regularity, training patterns): ABAB with 7-day phases.
  - Washout nights after switches where carryover is plausible.
- **The data decides the length:** simulate the plan with the user's own day-to-day variability
  and autocorrelation, then choose the length needed to detect the smallest meaningful
  effect. There is no fixed "14 days", and no promise that 4 weeks is enough. If the
  required length is unrealistic, suggest a less noisy metric or a bigger change.
- Opening with "we noticed an association" needs existing logs (for example, caffeine
  check-ins), so the system cannot say this before such data exists.

**2. Execute and track**
- The daily email shows today's condition (and Phase 2 can add a confirmed reminder to the calendar).
- One-tap yes/no check-in (Phase 3 mechanism); adherence from WHOOP or the calendar where possible.
- Automatic flags: travel or time zone change, illness signals, packed days, missing nights.
- Mid-experiment nudges when adherence drops.

**3. Analyze (deterministic engine)**
- Bayesian regression with AR(1) errors, controlling for strain, calendar load and day of week.
- Intention-to-treat and per-protocol results; the effect with a credible interval; the
  probability of a benefit and of a meaningful benefit.
- **Before release:** calibrate the intervals so that 90% intervals cover about 90% of
  simulated truths, and validate on synthetic data with planted effects. Support
  randomized-day and short-block designs (the WIP engine supports only 7-14 day phases).

**4. Quality assessment ("report card")**
- Adherence per condition, usable days per condition, and missing or flagged nights.
- **Balance check:** were strain, calendar load and weekends similar across conditions?
- Was carryover handled? Do ITT and per-protocol agree?
- **Grade:** *conclusive*, *suggestive* or *insufficient data*, with the specific reasons.

**5. Follow-up**
- Recommend one of: **adopt**, **extend** (code estimates how many more days are needed, as
  allowed by the pre-registered stopping rule), **repeat** to confirm, **refine** (change the
  dose or timing), or **drop**.

**Data:** `experiments`, `experiment_days` and `daily_checkins` (from the WIP branch), plus
a pre-registration snapshot, the assessment and follow-up decisions.

## Phase 5: Adaptive personalization and AI memory

Goal: the assistant knows *you*, not just yesterday's numbers.

- **Memory = structured insights computed in code,** not raw data handed to the LLM. A
  `user_insights` table stores one row per insight:
  - the statement (e.g. "you sleep about 35 min less on Tuesdays and Wednesdays");
  - the source: a data pattern, user feedback, a preference or an experiment;
  - the strength: an experiment result is causal; patterns and feedback are labeled as correlations or preferences;
  - when it was last updated, and when it should be re-checked.
- **Examples:**
  - "Prefers training in the afternoon" (from accepted and declined proposals).
  - "Declined 7am workouts three times" (so stop proposing them).
  - "Last caffeine experiment: insufficient data" (so suggest repeating it with a better design).
  - "Evening hard training lowers your next-day HRV" (conclusive experiment, so it shapes scheduling).
- Before each LLM call, code selects the few insights relevant to today and sends a compact
  digest. This is more reliable and much cheaper than sending 30 days of records.
- The planner's scoring and slot choice also read these insights directly, without the LLM.
- Users can see and delete their insights (and PRIVACY.md describes them).

## Later (not now)

- Full web dashboard (history, experiments, insights); Telegram as a second channel.
- Hosted multi-user version: web OAuth, a settings page, per-user email via a transactional
  email provider, Google verification for sensitive scopes, account deletion, and Alembic
  migrations.
- Observational pattern discovery (bedtime regularity, workout timing, meeting load,
  weather) as experiment ideas, labeled as unverified.
- Sport-specific blocks with a reviewed exercise library (e.g. golf), and equipment guidance.
- Nutrition guidance (would need safety floors, opt-in, a nutrition database, and no LLM-generated values).
- Other wearables (Oura, Garmin, Apple Health) behind a common ingestion interface.

## Order of work

1. ~~**Phase 1 additions:** trends, load, weekday patterns.~~ Done.
2. **Phase 2:** ~~focus selection and threshold, slot finding, the "Today's focus" email~~ (done);
   next: signed action links with a minimal endpoint, the dedicated calendar, and finally the LLM wording.
3. **Phase 3:** decision log, completion checks, "was it helpful?".
4. **Phase 4:** calibrate and merge the engine; presets; pre-registration; data-driven
   length; report card; follow-up.
5. **Phase 5:** the insights table, then preferences from feedback, then the LLM digest.

Work starts on the author's go-ahead.
