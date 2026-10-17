"""Experiment presets. Each one fixes, before the experiment starts:

* the intervention (what to do on treatment nights) and the control (your usual evening);
* how adherence is known: the user's one-tap confirmation, never inferred from the outcome;
* the primary outcome and a secondary one, both read from the wearable;
* the smallest effect worth caring about, used to call a result "no meaningful effect".

Outcome convention (src/analysis/panel.py): panel row `d` holds the sleep that starts on the
night of `d` and the recovery measured after it, so the outcome of night `d` is row `d`.
"""
PRESETS: dict[str, dict] = {
    "screens_off_30": dict(
        title="No screens 30 minutes before bed",
        short="screen-free",
        question="Do screen-free last 30 minutes before bed improve your sleep?",
        treatment="Screens off (phone, laptop, TV) for the last 30 minutes before bed.",
        control="your usual evening; screens are fine.",
        adherence_question="Did you keep screens off for the last 30 minutes before bed last night?",
        outcome=dict(column="sleep_performance_pct", label="Sleep performance", unit="points", meaningful=3.0),
        secondary=dict(column="hrv_rmssd_milli", label="HRV", unit="ms", meaningful=3.0),
        nights=14,
    ),
}


def preset(key: str) -> dict:
    if key not in PRESETS:
        raise KeyError(f"Unknown experiment {key!r}. Available: {', '.join(PRESETS)}")
    return PRESETS[key]
