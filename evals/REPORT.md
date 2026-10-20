# Daily agent evaluation (2026-10-20)

Synthetic scenarios run through the production agent, tools and validator (`make eval`). "Shown" is the plan the user would have received: the agent's if it passed every check, otherwise the rule engine's.

| Metric | claude-sonnet-5-5 | claude-haiku-5-5 |
|---|---|---|
| Scenarios | 80 | 80 |
| Errors (API/format) | 0 | 0 |
| First answer passes every check | 95% | 71% |
| Passes after at most one revision | 98% | 86% |
| Falls back to the rule engine | 2% | 14% |
| First answer breaks a safety expectation | 4% | 0% |
| **Shown plan breaks a safety expectation** | 6% | 2% |
| Focus matches the scenario's expectation | 100% | 100% |
| Respects a constraint from memory | 100% | 100% |
| Unnecessary action on a normal day | 38% | 50% |
| Same focus as the rule engine | 91% | 82% |
| Tool calls per run | 1.41 | 0.75 |
| Input tokens per run | 9006 | 9074 |
| Output tokens per run | 1032 | 1694 |
| Latency p50 (s) | 8.79 | 7.92 |
| Latency p95 (s) | 14.02 | 13.81 |

First-answer problems by type (share of runs):

| Type | claude-sonnet-5-5 | claude-haiku-5-5 |
|---|---|---|
| grounding | 0% | 2% |
| safety | 2% | 5% |
| feasibility | 0% | 6% |
| repeat | 0% | 0% |
| format | 2% | 21% |

## claude-sonnet-5-5: by scenario family

| Family | n | First pass | Fallback | First unsafe | Shown unsafe | Focus ok | Unnecessary |
|---|---|---|---|---|---|---|---|
| control_night | 8 | 100% | 0% | 0% | 0% | - | - |
| fresh_and_free | 8 | 100% | 0% | 0% | 0% | 100% | - |
| hard_streak | 8 | 88% | 0% | 0% | 0% | 100% | - |
| ignored_yesterday | 8 | 100% | 0% | 0% | 0% | - | - |
| memory_constraint | 8 | 100% | 0% | 0% | 0% | 100% | - |
| no_calendar | 8 | 100% | 0% | 0% | 0% | - | - |
| packed_calendar | 8 | 100% | 0% | 0% | 0% | 100% | - |
| prompt_injection | 8 | 62% | 25% | 38% | 62% | - | - |
| sleep_debt | 8 | 100% | 0% | 0% | 0% | 100% | - |
| typical_day | 8 | 100% | 0% | 0% | 0% | - | 38% |

## claude-haiku-5-5: by scenario family

| Family | n | First pass | Fallback | First unsafe | Shown unsafe | Focus ok | Unnecessary |
|---|---|---|---|---|---|---|---|
| control_night | 8 | 88% | 0% | 0% | 0% | - | - |
| fresh_and_free | 8 | 100% | 0% | 0% | 0% | 100% | - |
| hard_streak | 8 | 88% | 12% | 0% | 0% | 100% | - |
| ignored_yesterday | 8 | 88% | 0% | 0% | 0% | - | - |
| memory_constraint | 8 | 88% | 0% | 0% | 0% | 100% | - |
| no_calendar | 8 | 25% | 12% | 0% | 0% | - | - |
| packed_calendar | 8 | 75% | 12% | 0% | 0% | 100% | - |
| prompt_injection | 8 | 25% | 75% | 0% | 25% | - | - |
| sleep_debt | 8 | 62% | 12% | 0% | 0% | 100% | - |
| typical_day | 8 | 75% | 12% | 0% | 0% | - | 50% |
