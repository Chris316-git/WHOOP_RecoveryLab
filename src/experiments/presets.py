"""Experiment presets. Each one fixes, before the experiment starts:

* the intervention (what to do on treatment days) and the control (your usual routine);
* how adherence is known: the user's one-tap confirmation, never inferred from the outcome;
* the primary outcome and a secondary one, both read from the wearable;
* the smallest effect worth caring about, used to call a result "no meaningful effect".

The AI may propose one of these, with a reason drawn from your data; it cannot invent new
interventions or outcomes, and the randomization and statistics stay in code.

Outcome convention (src/analysis/panel.py): panel row `d` holds the sleep that starts on the
night of `d` and the recovery measured after it, so the outcome of day `d` is row `d`.
"""
PRESETS: dict[str, dict] = {
    "screens_off_30": dict(
        title="No screens 30 minutes before bed",
        short="screen-free",
        question="Do screen-free last 30 minutes before bed improve your sleep?",
        treatment="Screens off (phone, laptop, TV) for the last 30 minutes before bed.",
        control="your usual evening; screens are fine.",
        tonight_treatment="Tonight is a screen-free night: screens off from {bed_minus_30}, 30 minutes before your "
                          "usual bedtime ({bed}).",
        conflict_words=("screen",),
        adherence_question="Did you keep screens off for the last 30 minutes before bed last night?",
        outcome=dict(column="sleep_performance_pct", label="Sleep performance", unit="points", meaningful=3.0),
        secondary=dict(column="hrv_rmssd_milli", label="HRV", unit="ms", meaningful=3.0),
        nights=14,
    ),
    "no_late_hard_training": dict(
        title="No hard training after 20:00",
        short="no-late-training",
        question="Does keeping hard workouts before 20:00 help your overnight recovery?",
        treatment="No hard or intense workout that starts after 20:00 (easy movement is fine).",
        control="your usual training times.",
        tonight_treatment="Today is a no-late-training day: if you train hard, finish by 20:00.",
        conflict_words=("after 20:00", "late training", "late workout"),
        adherence_question="Did you avoid hard exercise after 20:00 yesterday?",
        outcome=dict(column="hrv_rmssd_milli", label="HRV", unit="ms", meaningful=3.0),
        secondary=dict(column="recovery_score", label="Recovery", unit="points", meaningful=5.0),
        nights=14,
    ),
    "no_afternoon_caffeine": dict(
        title="No caffeine after 14:00",
        short="caffeine-free afternoon",
        question="Does skipping caffeine after 14:00 improve your sleep?",
        treatment="No coffee, tea, energy drinks or other caffeine after 14:00.",
        control="your usual caffeine habits.",
        tonight_treatment="Today is a caffeine-free afternoon: no caffeine after 14:00.",
        conflict_words=("caffeine", "coffee"),
        adherence_question="Did you skip caffeine after 14:00 yesterday?",
        outcome=dict(column="sleep_performance_pct", label="Sleep performance", unit="points", meaningful=3.0),
        secondary=dict(column="deep_min", label="Deep sleep", unit="min", meaningful=5.0),
        nights=14,
    ),
}
EXTENSION_NIGHTS = 6        # "extend" adds three more pairs, at most MAX_EXTENSIONS times
MAX_EXTENSIONS = 1


def preset(key: str) -> dict:
    if key not in PRESETS:
        raise KeyError(f"Unknown experiment {key!r}. Available: {', '.join(PRESETS)}")
    return PRESETS[key]
