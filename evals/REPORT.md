# Daily agent evaluation (2026-10-20)

Synthetic scenarios run through the production agent, tools and validator (`make eval`). "Shown" is the plan the user would have received: the agent's if it passed every check, otherwise the rule engine's.

Combined from two runs on the same code: `typical_day` from `2026-10-20-1415` (after a scenario fix made those mornings truly typical), the other nine families from `2026-10-20-1210`. 80 scenarios per model.

| Metric | claude-sonnet-5-5 | claude-haiku-5-5 |
|---|---|---|
| Scenarios | 80 | 80 |
| Errors (API/format) | 0 | 0 |
| First answer passes every check | 96% | 80% |
| Passes after at most one revision | 100% | 98% |
| Falls back to the rule engine | 0% | 2% |
| First answer breaks a safety expectation | 0% | 0% |
| **Shown plan breaks a safety expectation** | 0% | 0% |
| Focus matches the scenario's expectation | 100% | 100% |
| Respects a constraint from memory | 100% | 100% |
| Repeats injected text (while refusing it) | 0% | 0% |
| Unnecessary action on a normal day | 12% | 0% |
| Same focus as the rule engine | 94% | 79% |
| Tool calls per run | 1.21 | 0.64 |
| Input tokens per run | 8943 | 8257 |
| Output tokens per run | 1006 | 1586 |
| Latency p50 (s) | 8.54 | 7.67 |
| Latency p95 (s) | 12.83 | 12.13 |

First-answer problems by type (share of runs):

| Type | claude-sonnet-5-5 | claude-haiku-5-5 |
|---|---|---|
| grounding | 0% | 2% |
| safety | 2% | 1% |
| feasibility | 1% | 9% |
| repeat | 0% | 0% |
| format | 0% | 10% |

## claude-sonnet-5-5: by scenario family

| Family | n | First pass | Fallback | First unsafe | Shown unsafe | Focus ok | Unnecessary |
|---|---|---|---|---|---|---|---|
| control_night | 8 | 100% | 0% | 0% | 0% | - | - |
| fresh_and_free | 8 | 88% | 0% | 0% | 0% | 100% | - |
| hard_streak | 8 | 100% | 0% | 0% | 0% | 100% | - |
| ignored_yesterday | 8 | 100% | 0% | 0% | 0% | - | - |
| memory_constraint | 8 | 100% | 0% | 0% | 0% | 100% | - |
| no_calendar | 8 | 100% | 0% | 0% | 0% | - | - |
| packed_calendar | 8 | 100% | 0% | 0% | 0% | 100% | - |
| prompt_injection | 8 | 88% | 0% | 0% | 0% | - | - |
| sleep_debt | 8 | 100% | 0% | 0% | 0% | 100% | - |
| typical_day | 8 | 88% | 0% | 0% | 0% | - | 12% |

## claude-haiku-5-5: by scenario family

| Family | n | First pass | Fallback | First unsafe | Shown unsafe | Focus ok | Unnecessary |
|---|---|---|---|---|---|---|---|
| control_night | 8 | 100% | 0% | 0% | 0% | - | - |
| fresh_and_free | 8 | 88% | 0% | 0% | 0% | 100% | - |
| hard_streak | 8 | 88% | 0% | 0% | 0% | 100% | - |
| ignored_yesterday | 8 | 100% | 0% | 0% | 0% | - | - |
| memory_constraint | 8 | 100% | 0% | 0% | 0% | 100% | - |
| no_calendar | 8 | 12% | 25% | 0% | 0% | - | - |
| packed_calendar | 8 | 75% | 0% | 0% | 0% | 100% | - |
| prompt_injection | 8 | 100% | 0% | 0% | 0% | - | - |
| sleep_debt | 8 | 50% | 0% | 0% | 0% | 100% | - |
| typical_day | 8 | 88% | 0% | 0% | 0% | - | 0% |
