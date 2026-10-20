# Daily agent evaluation (2026-10-20)

Synthetic scenarios run through the production agent, tools and validator (`make eval`). "Shown" is the plan the user would have received: the agent's if it passed every check, otherwise the rule engine's.

| Metric | claude-sonnet-5-5 |
|---|---|
| Scenarios | 20 |
| Errors (API/format) | 1 |
| First answer passes every check | 95% |
| Passes after at most one revision | 95% |
| Falls back to the rule engine | 10% |
| First answer breaks a safety expectation | 0% |
| **Shown plan breaks a safety expectation** | 0% |
| Focus matches the scenario's expectation | 100% |
| Respects a constraint from memory | 100% |
| Unnecessary action on a normal day | 0% |
| Same focus as the rule engine | 95% |
| Tool calls per run | 1.58 |
| Input tokens per run | 10046 |
| Output tokens per run | 1081 |
| Latency p50 (s) | 9.42 |
| Latency p95 (s) | 18.67 |

First-answer problems by type (share of runs):

| Type | claude-sonnet-5-5 |
|---|---|
| grounding | 0% |
| safety | 0% |
| feasibility | 0% |
| repeat | 0% |
| format | 5% |

## claude-sonnet-5-5: by scenario family

| Family | n | First pass | Fallback | First unsafe | Shown unsafe | Focus ok | Unnecessary |
|---|---|---|---|---|---|---|---|
| control_night | 2 | 100% | 0% | 0% | 0% | - | - |
| fresh_and_free | 2 | 100% | 0% | 0% | 0% | 100% | - |
| hard_streak | 2 | 100% | 0% | 0% | 0% | 100% | - |
| ignored_yesterday | 2 | 100% | 0% | 0% | 0% | - | - |
| memory_constraint | 2 | 100% | 50% | 0% | 0% | 100% | - |
| no_calendar | 2 | 100% | 0% | 0% | 0% | - | - |
| packed_calendar | 2 | 100% | 0% | 0% | 0% | 100% | - |
| prompt_injection | 2 | 50% | 50% | 0% | 0% | - | - |
| sleep_debt | 2 | 100% | 0% | 0% | 0% | 100% | - |
| typical_day | 2 | 100% | 0% | 0% | 0% | - | 0% |
