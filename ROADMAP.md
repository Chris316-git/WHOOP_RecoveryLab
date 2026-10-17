# Roadmap

Recovery Lab is a personal health decision system. It turns wearable data and your real
calendar into one clear decision a day, and then checks whether that decision helped. It is
not a dashboard of more numbers, and it is not "WHOOP data pasted into a chatbot". It is
built to answer three questions:

1. **What should I do today?** One focus, placed in real free time, or "nothing needs to change".
2. **Why should I do it?** Reasons computed from your own data, compared with your own baseline.
3. **Did it actually help?** Feedback every day, and proper experiments when you want certainty.

**It analyzes every day and steps in only when it matters.** It is not a planner that fills
your day with tasks to accept. Two modes:

- **Daily Brief (passive, the core).** Every morning, analysis is done and sent. Most days you
  just read it in about 15 seconds and close it; that is a complete, valid response. When the
  one focus needs a time block, a single optional tap puts it on your calendar.
- **Assistant (active, later).** When *you* want to plan training, rework a week, dig into
  sleep or start a habit experiment, you ask, and the assistant calls the same tools
  (signals, planner, calendar, experiments). See "Later".

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
any time. What is harder to copy is the combination: one well-chosen focus, an optional
one-tap calendar step, a feedback loop read from data, and personalization grounded in experiments.

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
- **Low effort, user in control.** Reading is enough; acting is optional. The calendar is a
  tool, not the core: only advice that needs a time block offers it, it takes one tap, and
  every action can be undone. Nothing lands on the calendar unless the user taps.
- **No response is not a rejection.** Suggested, scheduled and done are separate states, and
  "did it happen" is read from wearable data wherever possible instead of asking.
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
- Daily planner: one focus a day with confidence, counter-evidence and "why not"
- Optional one-tap "Add to calendar" / "Change time" / "Dismiss", with Undo, on a dedicated calendar
- Yesterday's focus checked from wearable data and shown as one line (Phase 3, first part)
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

Goal: one recommendation a day that fits your body and your calendar. Reading it is enough;
scheduling it is optional.

**Status:** steps 1-3 are done: focus selection with confidence, counter-evidence and "why
not"; slot finding; the email card; optional one-tap calendar actions with Undo
(`src/actions/`). Simplified after the first version: no "Accept" (accept what, the analysis
or a promise?), no confirmation step, no reasons asked on skip, and no buttons on days with
nothing to change. Still open from step 3: moving a scheduled block
automatically when a new meeting conflicts. Step 4 (LLM wording) is done (`src/llm/wording.py`).

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

**2. Find time and the activity.** Use free windows from the real calendar, from 07:00 to
midnight, placed as close as possible to the time you usually train. The activity comes from
your last 8 weeks of WHOOP workouts (`src/planner/habits.py`): an easy day suggests an easy
habit (e.g. yoga) or the easy version of your main activity ("easy running, conversational
pace"), a hard day your usual hard session. With too little history it falls back to a walk.
No exercise library: the rules only adjust intensity and duration per activity category.
Hard sessions stay at least 3 hours before the target bedtime. Respect the user's preferred hours and allowed days. If
nothing fits, offer a shorter version or suggest tomorrow. "Prioritize sleep" becomes a
wind-down block that starts 45-60 minutes before the target bedtime (target wake time minus
sleep need).

**3. Optional calendar actions.**
- Focuses that come with a time block (an easy walk, a wind-down, a break in a busy day, a
  hard session) get **Add to calendar** and **Change time**, plus a quiet **Dismiss**. Days
  with nothing to change get no buttons.
- Links are **signed and expiring** (an HMAC token over user, day, action and expiry). Mail
  scanners open links on their own, so a GET never acts by itself: the page submits the
  action with a line of JavaScript (most scanners do not run it) and falls back to a button.
  Every result offers **Undo**. Dismiss asks nothing; "the suggestion itself wasn't useful"
  is an optional extra tap.
- Events go to a dedicated **"Recovery Lab"** calendar using the narrow
  `calendar.app.created` scope (the app can only touch events on its own calendar). A
  wind-down is marked "free" so it reminds without blocking the evening.
- Fallback with no server: an `.ics` "add to calendar" attachment (the user's click adds it;
  the app cannot move it later).
- After confirmation, the block is moved or shortened if a new meeting conflicts or
  readiness drops. Blocks the user moved by hand are never touched, and events are updated
  in place, never duplicated.

**4. Wording (done).** The LLM turns the computed focus, reasons and slot into a short, friendly
message (e.g. "Good morning: your recovery is below your recent level and yesterday was a
hard day, so today should be light. You are free at 17:30. Shall I add a 30-minute easy
session?"). Guardrails: the numeric consistency check, structured input only, and a
template fallback when the API fails, so the email always goes out.

**Data:** `daily_plans` keeps three things apart: the recommendation (focus, score, reasons,
suggested block), the response (`None` = no response, `added`, `dismissed`, `not_useful`)
and the calendar state (`scheduled`, `removed`, the event ID). The outcome is a fourth,
separate field filled in the next morning (Phase 3).

## Phase 2b: AI reasoning engine (done)

The rule engine became the fallback. A Claude model reads a numbered evidence file built in
code and decides the day's focus and action itself (not just choosing from a list), so it can
notice things the rules do not encode, such as advice that keeps not being followed, and
propose a smaller, more realistic step. A code validator checks evidence ids, numbers, safety
and calendar feasibility before anything is shown. Both engines' choices, the evidence and the
validator's verdict are stored per day; `scripts/evaluate.py` reports pass rate, rejection
reasons, blocked unsafe suggestions, agreement with the rules, personalization and outcomes by
engine. Next: a randomized mode (rules or AI per day) for a fair comparison of adherence, and
an optional one-tap question when the AI lacks information.

## Phase 3: Feedback loop

Goal: know, every day, whether recommendations are followed and whether they help, without
turning the product into a check-in app.

**Status:** the first part is done (`src/feedback/outcome.py`): responses are logged, and
the next morning the email shows one line on yesterday's focus, measured from data.

- **Log every response:** added (and the time), dismissed, not useful, or no response.
  Silence is never counted as a rejection.
- **Did it happen? (done)** Read from data, not asked: "take it easy" and "hard session"
  from that day's strain, "protect your sleep" from the actual bedtime vs. the target.
  "Build breaks" cannot be seen in the data and is reported only when it was scheduled.
  No evening check-in email: one more message is one more interruption.
- **Learning from responses (started):** a focus marked "not useful" needs stronger
  evidence for two weeks. Later: lower the weight of a suggestion type the user repeatedly
  dismisses, and adjust slot times from where blocks were moved.
- **Did it help?** Possibly a one-tap "helpful?" on days something was scheduled, only if
  the data-based line proves not to be enough.
- **Outcome tracking:** next-day readiness after followed vs. not-followed recommendations.
  This is reported descriptively, as an association; Phase 4 provides the causal evidence.
- The same one-tap mechanism later serves experiment check-ins.

**Data:** `daily_plans.outcome` (done, partly, not done, no data, unmeasured) with the few
numbers behind it in `outcome_detail`.

## Phase 4: Personal experiment engine

**Status: v0.1 done** (`src/experiments/`). Deliberately simple and checkable: one preset
("no screens 30 minutes before bed", outcome sleep performance), randomized paired nights,
adherence from a one-tap answer (not inferred from the wearable), and a randomization test
with a t-interval, validated by simulation (about 5% false positives, about 95% coverage;
with 7 pairs, power is low for small effects, so "inconclusive" is common and honest).
The original ABAB plus Bayesian AR(1) design stays on the shelf until v0.1 has run end to end.
Next: AI-proposed hypotheses and plain-language explanations (statistics stay in code), more
presets, and extending an experiment when the interval is still too wide.

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
  - "Prefers training in the afternoon" (from blocks added, moved and dismissed).
  - "Declined 7am workouts three times" (so stop proposing them).
  - "Last caffeine experiment: insufficient data" (so suggest repeating it with a better design).
  - "Evening hard training lowers your next-day HRV" (conclusive experiment, so it shapes scheduling).
- Before each LLM call, code selects the few insights relevant to today and sends a compact
  digest. This is more reliable and much cheaper than sending 30 days of records.
- The planner's scoring and slot choice also read these insights directly, without the LLM.
- Users can see and delete their insights (and PRIVACY.md describes them).

## Later (not now)

- **Assistant mode:** expose the existing pipeline as tools (today's signals, the planner,
  free time, add or move a calendar block, experiment status), e.g. as an MCP server, so the
  user can ask an assistant when they want to plan, instead of us building a chat UI.

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
2. **Phase 2:** ~~focus selection, slot finding, the email card, optional calendar actions,
   LLM wording~~ (done); still open: moving a scheduled block when a new meeting conflicts.
3. **Phase 3:** ~~response log, completion checks from data~~ (done); next: learn from
   repeated dismissals and moved blocks; "did it help" over many days, labeled as association.
4. **Phase 4:** calibrate and merge the engine; presets; pre-registration; data-driven
   length; report card; follow-up.
5. **Phase 5:** the insights table, then preferences from feedback, then the LLM digest.

Work starts on the author's go-ahead.
